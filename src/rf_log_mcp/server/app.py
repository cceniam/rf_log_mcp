"""FastMCP application wiring."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from rf_log_mcp.constants import DB_ENV_VAR, DEFAULT_BUDGET, DEFAULT_PAGE_SIZE, default_db_path
from rf_log_mcp.domain.schemas import (
    ErrorPayload,
    ParseResultPayload,
    TestResourcePayload,
)
from rf_log_mcp.errors import InvalidQueryError, InvalidViewError, RfLogMcpError, TestNotFoundError
from rf_log_mcp.parsers.gating import probe_input, sha256_file
from rf_log_mcp.parsers.json_adapter import parse_output_json
from rf_log_mcp.parsers.xml_adapter import parse_output_xml
from rf_log_mcp.storage.sqlite_store import RunStore
from rf_log_mcp.views import (
    build_failure_path,
    build_search_payload,
    build_step_window,
    build_summary,
    estimate_tokens,
)

LOGGER = logging.getLogger("rf_log_mcp")


class RfLogService:
    def __init__(self, store: RunStore) -> None:
        self.store = store

    def parse_result(self, path: str, force_rebuild: bool = False) -> dict[str, Any]:
        probed = probe_input(path)
        content_hash = sha256_file(probed.path)
        existing_run_id = self.store.get_run_id_by_hash(content_hash)
        cached = existing_run_id is not None
        if cached and not force_rebuild:
            run = self.store.get_run(existing_run_id)
        else:
            parser = parse_output_json if probed.source_format == "json" else parse_output_xml
            run = parser(probed)
            run_id = self.store.put_run(run, replace_existing=force_rebuild)
            run = self.store.get_run(run_id)
        payload = ParseResultPayload(
            input_profile=run.metadata.input_profile,
            run_id=run.run_id,
            estimated_tokens=0,
            truncated=False,
            source_format=run.metadata.source_format,
            source_path=run.metadata.source_path,
            generator=run.metadata.generator,
            generated=run.metadata.generated,
            schemaversion=run.metadata.schemaversion,
            cached=cached and not force_rebuild,
            available_views=["summary", "failure_path", "step_window"],
            resource_uris=[
                f"rf://runs/{run.run_id}/summary",
            ]
            + [f"rf://runs/{run.run_id}/tests/{node.id}" for node in run.test_nodes],
        )
        payload.estimated_tokens = estimate_tokens(payload.model_dump())
        return payload.model_dump()

    def get_view(
        self,
        run_id: int | str,
        view: str,
        selector: str | None = None,
        cursor: str | None = None,
        budget: int = DEFAULT_BUDGET,
    ) -> dict[str, Any]:
        resolved_run_id = self.store.resolve_run_ref(run_id)
        if view not in {"summary", "failure_path", "step_window"}:
            raise InvalidViewError(view)
        if view != "step_window":
            cached = self.store.get_cached_view(resolved_run_id, view, selector, budget)
            if cached is not None:
                return cached
        run = self.store.get_run(resolved_run_id)
        if view == "summary":
            payload = build_summary(run, budget=budget).model_dump()
        elif view == "failure_path":
            payload = build_failure_path(run, selector=selector, budget=budget).model_dump()
        else:
            if not selector:
                raise TestNotFoundError("<missing-selector>")
            payload = build_step_window(
                run,
                selector=selector,
                cursor=cursor,
                budget=budget,
                page_size=DEFAULT_PAGE_SIZE,
            ).model_dump()
        if view != "step_window":
            self.store.set_cached_view(resolved_run_id, view, selector, budget, payload)
        return payload

    def search_messages(
        self,
        run_id: int | str,
        query: str,
        level: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not query.strip():
            raise InvalidQueryError()
        from rf_log_mcp.views import decode_cursor

        resolved_run_id = self.store.resolve_run_ref(run_id)
        offset = decode_cursor(cursor)
        run = self.store.get_run(resolved_run_id)
        results, has_more = self.store.search_messages(
            resolved_run_id,
            query,
            level=level.upper() if level else None,
            limit=min(max(limit, 1), 100),
            offset=offset,
        )
        payload = build_search_payload(
            run,
            query=query,
            level=level.upper() if level else None,
            results=results,
            has_more=has_more,
            offset=offset,
        )
        return payload.model_dump()

    def get_test_resource(self, run_id: int | str, test_id: str) -> dict[str, Any]:
        resolved_run_id = self.store.resolve_run_ref(run_id)
        run = self.store.get_run(resolved_run_id)
        node = next((item for item in run.test_nodes if item.id == test_id), None)
        if node is None:
            raise TestNotFoundError(test_id)
        failure_path = build_failure_path(run, selector=test_id).failure_chain
        payload = TestResourcePayload(
            run_id=resolved_run_id,
            input_profile=run.metadata.input_profile,
            test={
                "test_id": node.id,
                "name": node.name,
                "longname": node.longname,
                "status": node.status,
                "message": node.message,
                "tags": node.tags,
                "ref_uri": node.ref_uri,
            },
            failure_path=failure_path,
        )
        return payload.model_dump()


def _db_path() -> Path:
    override = os.getenv(DB_ENV_VAR)
    return Path(override).expanduser().resolve() if override else default_db_path()


def _service() -> RfLogService:
    return RfLogService(RunStore(_db_path()))


SERVICE = _service()
mcp = FastMCP(
    name="rf-log-mcp",
    instructions=(
        "Inspect Robot Framework XML (schema 3/4/5) and RF 7.2+ JSON result files "
        "with minimal evidence views."
    ),
)


def _error_payload(error: RfLogMcpError) -> dict[str, Any]:
    return ErrorPayload(error_code=error.code, error_message=error.message).model_dump()


@mcp.tool(
    description="Parse a Robot Framework output.xml or RF 7.2+ output.json file and index it.",
    structured_output=True,
)
def parse_result(path: str, force_rebuild: bool = False) -> dict[str, Any]:
    try:
        return SERVICE.parse_result(path, force_rebuild=force_rebuild)
    except RfLogMcpError as error:
        LOGGER.warning("parse_result failed: %s", error.message)
        return _error_payload(error)


@mcp.tool(
    description="Get one supported view using a numeric run id or an already-parsed file path.",
    structured_output=True,
)
def get_view(
    run_id: int | str,
    view: str,
    selector: str | None = None,
    cursor: str | None = None,
    budget: int = DEFAULT_BUDGET,
) -> dict[str, Any]:
    try:
        return SERVICE.get_view(run_id, view=view, selector=selector, cursor=cursor, budget=budget)
    except RfLogMcpError as error:
        LOGGER.warning("get_view failed: %s", error.message)
        return _error_payload(error)


@mcp.tool(
    description="Search indexed messages using a numeric run id or an already-parsed file path.",
    structured_output=True,
)
def search_messages(
    run_id: int | str,
    query: str,
    level: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> dict[str, Any]:
    try:
        return SERVICE.search_messages(run_id, query=query, level=level, limit=limit, cursor=cursor)
    except RfLogMcpError as error:
        LOGGER.warning("search_messages failed: %s", error.message)
        return _error_payload(error)


@mcp.resource("rf://runs/{run_id}/summary", mime_type="application/json")
def summary_resource(run_id: str) -> dict[str, Any]:
    return SERVICE.get_view(run_id, view="summary")


@mcp.resource("rf://runs/{run_id}/tests/{test_id}", mime_type="application/json")
def test_resource(run_id: int | str, test_id: str) -> dict[str, Any]:
    return SERVICE.get_test_resource(run_id, test_id)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )


def main() -> None:
    configure_logging()
    mcp.run(transport="stdio")
