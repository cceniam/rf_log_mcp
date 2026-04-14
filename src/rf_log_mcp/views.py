"""View builders and cursor helpers."""

from __future__ import annotations

import base64
import json
from collections import defaultdict
from typing import Any

from rf_log_mcp.constants import DEFAULT_BUDGET, DEFAULT_PAGE_SIZE
from rf_log_mcp.domain.models import MessageRecord, NodeRecord, NormalizedRun
from rf_log_mcp.domain.schemas import (
    FailurePathPayload,
    SearchMessagesPayload,
    StepWindowPayload,
    SummaryPayload,
)
from rf_log_mcp.errors import InvalidCursorError, TestNotFoundError


def estimate_tokens(payload: dict[str, Any]) -> int:
    return max(1, len(json.dumps(payload, ensure_ascii=False)) // 4)


def truncate_text(value: str | None, max_chars: int) -> str | None:
    if value is None or len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return f"{value[: max_chars - 3]}..."


def encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    padding = "=" * (-len(cursor) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(f"{cursor}{padding}").decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive branch
        raise InvalidCursorError() from exc
    offset = data.get("offset")
    if not isinstance(offset, int) or offset < 0:
        raise InvalidCursorError()
    return offset


def build_summary(run: NormalizedRun, *, budget: int = DEFAULT_BUDGET) -> SummaryPayload:
    truncated = False
    failed_tests = []
    for node in run.failed_tests:
        failed_tests.append(
            {
                "test_id": node.id,
                "name": node.name,
                "longname": node.longname,
                "status": node.status,
                "message": truncate_text(node.message, 320),
                "ref_uri": node.ref_uri,
            }
        )
        if node.message and len(node.message) > 320:
            truncated = True
    errors = []
    for item in run.errors:
        errors.append(
            {
                "error_id": item.id,
                "level": item.level,
                "message": truncate_text(item.message, 320),
                "ref_uri": item.ref_uri,
            }
        )
        if len(item.message) > 320:
            truncated = True
    while len(failed_tests) > 10:
        failed_tests.pop()
        truncated = True
    payload = SummaryPayload(
        input_profile=run.metadata.input_profile,
        run_id=run.run_id,
        estimated_tokens=0,
        truncated=truncated,
        metadata={
            "source_path": run.metadata.source_path,
            "source_name": run.metadata.source_name,
            "source_format": run.metadata.source_format,
            "generator": run.metadata.generator,
            "generated": run.metadata.generated,
            "generation_time": run.metadata.generation_time,
            "schemaversion": run.metadata.schemaversion,
            "rpa": run.metadata.rpa,
        },
        statistics=run.statistics,
        failed_tests=failed_tests,
        errors=errors[:10],
    )
    payload.estimated_tokens = estimate_tokens(payload.model_dump())
    if payload.estimated_tokens > budget:
        payload.truncated = True
        payload.failed_tests = payload.failed_tests[:5]
        payload.errors = payload.errors[:5]
        payload.estimated_tokens = estimate_tokens(payload.model_dump())
    return payload


def _node_lookup(run: NormalizedRun) -> dict[str, NodeRecord]:
    return {node.id: node for node in run.nodes}


def _children_lookup(run: NormalizedRun) -> dict[str | None, list[NodeRecord]]:
    children: dict[str | None, list[NodeRecord]] = defaultdict(list)
    for node in sorted(run.nodes, key=lambda item: item.sequence):
        children[node.parent_id].append(node)
    return children


def _messages_by_parent(run: NormalizedRun) -> dict[str | None, list[MessageRecord]]:
    messages: dict[str | None, list[MessageRecord]] = defaultdict(list)
    for item in sorted(run.messages, key=lambda value: value.sequence):
        messages[item.parent_id].append(item)
    return messages


def _find_test(run: NormalizedRun, selector: str | None) -> NodeRecord:
    tests = {node.id: node for node in run.test_nodes}
    if selector:
        try:
            return tests[selector]
        except KeyError as exc:
            raise TestNotFoundError(selector) from exc
    failed = run.failed_tests
    if failed:
        return failed[0]
    if run.test_nodes:
        return run.test_nodes[0]
    raise TestNotFoundError(selector or "<no-tests>")


def _first_failed_branch(
    test_node: NodeRecord,
    children: dict[str | None, list[NodeRecord]],
) -> list[NodeRecord]:
    path: list[NodeRecord] = [test_node]
    current = test_node
    while True:
        next_failed = next(
            (
                child
                for child in children.get(current.id, [])
                if (child.status or "").upper() == "FAIL"
            ),
            None,
        )
        if next_failed is None:
            return path
        path.append(next_failed)
        current = next_failed


def build_failure_path(
    run: NormalizedRun,
    *,
    selector: str | None,
    budget: int = DEFAULT_BUDGET,
) -> FailurePathPayload:
    children = _children_lookup(run)
    messages_lookup = _messages_by_parent(run)
    test_node = _find_test(run, selector)
    chain = _first_failed_branch(test_node, children)
    seen_messages: set[str] = set()
    key_messages: list[dict[str, Any]] = []
    truncated = False
    for node in chain:
        for message in messages_lookup.get(node.id, []):
            normalized = message.message.strip()
            if not normalized or normalized in seen_messages:
                continue
            seen_messages.add(normalized)
            shortened = truncate_text(message.message, 360)
            if shortened != message.message:
                truncated = True
            key_messages.append(
                {
                    "message_id": message.id,
                    "level": message.level,
                    "message": shortened,
                    "ref_uri": message.ref_uri,
                }
            )
    if test_node.message and test_node.message not in seen_messages:
        shortened = truncate_text(test_node.message, 360)
        if shortened != test_node.message:
            truncated = True
        key_messages.append(
            {
                "message_id": f"{test_node.id}-message",
                "level": "FAIL",
                "message": shortened,
                "ref_uri": test_node.ref_uri,
            }
        )
    payload = FailurePathPayload(
        input_profile=run.metadata.input_profile,
        run_id=run.run_id,
        estimated_tokens=0,
        truncated=truncated,
        selected_test_id=test_node.id,
        selected_test_name=test_node.longname or test_node.name,
        failure_chain=[
            {
                "node_id": node.id,
                "kind": node.kind,
                "name": node.name,
                "status": node.status,
                "ref_uri": node.ref_uri,
            }
            for node in chain
        ],
        key_messages=key_messages[:10],
    )
    payload.estimated_tokens = estimate_tokens(payload.model_dump())
    if payload.estimated_tokens > budget:
        payload.truncated = True
        payload.key_messages = payload.key_messages[:5]
        payload.estimated_tokens = estimate_tokens(payload.model_dump())
    return payload


def build_step_window(
    run: NormalizedRun,
    *,
    selector: str,
    cursor: str | None,
    budget: int = DEFAULT_BUDGET,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> StepWindowPayload:
    test_node = _find_test(run, selector)
    offset = decode_cursor(cursor)
    items: list[dict[str, Any]] = []
    for node in sorted(run.nodes, key=lambda item: item.sequence):
        if node.owner_test_id != test_node.id:
            continue
        items.append(
            {
                "kind": "node",
                "node_id": node.id,
                "node_kind": node.kind,
                "name": node.name,
                "status": node.status,
                "sequence": node.sequence,
                "ref_uri": node.ref_uri,
            }
        )
    for message in sorted(run.messages, key=lambda item: item.sequence):
        if message.owner_test_id != test_node.id:
            continue
        items.append(
            {
                "kind": "message",
                "message_id": message.id,
                "level": message.level,
                "message": truncate_text(message.message, 240),
                "sequence": message.sequence,
                "ref_uri": message.ref_uri,
            }
        )
    items.sort(key=lambda item: item["sequence"])
    page = items[offset : offset + page_size]
    next_cursor = encode_cursor(offset + page_size) if offset + page_size < len(items) else None
    payload = StepWindowPayload(
        input_profile=run.metadata.input_profile,
        run_id=run.run_id,
        estimated_tokens=0,
        truncated=next_cursor is not None,
        test_id=test_node.id,
        test_name=test_node.longname or test_node.name,
        items=page,
        next_cursor=next_cursor,
    )
    payload.estimated_tokens = estimate_tokens(payload.model_dump())
    if payload.estimated_tokens > budget and len(payload.items) > 1:
        payload.truncated = True
        payload.items = payload.items[: max(1, len(payload.items) // 2)]
        payload.next_cursor = encode_cursor(offset + len(payload.items))
        payload.estimated_tokens = estimate_tokens(payload.model_dump())
    return payload


def build_search_payload(
    run: NormalizedRun,
    *,
    query: str,
    level: str | None,
    results: list[dict[str, Any]],
    has_more: bool,
    offset: int,
) -> SearchMessagesPayload:
    payload = SearchMessagesPayload(
        input_profile=run.metadata.input_profile,
        run_id=run.run_id,
        estimated_tokens=0,
        truncated=has_more,
        query=query,
        level=level,
        results=[
            {
                "message_id": item["message_id"],
                "owner_test_id": item["owner_test_id"],
                "node_id": item["node_id"],
                "level": item["level"],
                "message": truncate_text(item["message"], 240),
                "timestamp": item["timestamp"],
                "ref_uri": item["ref_uri"],
            }
            for item in results
        ],
        next_cursor=encode_cursor(offset + len(results)) if has_more else None,
    )
    payload.estimated_tokens = estimate_tokens(payload.model_dump())
    return payload
