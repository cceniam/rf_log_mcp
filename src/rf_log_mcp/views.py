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


def _clamp_page_size(page_size: int, *, default: int, maximum: int = 100) -> int:
    return min(max(page_size or default, 1), maximum)


def _level_severity(level: str | None) -> int:
    return {
        "ERROR": 4,
        "FAIL": 3,
        "WARN": 2,
        "WARNING": 2,
        "INFO": 1,
        "DEBUG": 0,
        "TRACE": 0,
    }.get((level or "").upper(), 0)


def _shrink_messages(items: list[dict[str, Any]], max_chars: int) -> bool:
    changed = False
    for item in items:
        message = item.get("message")
        if not isinstance(message, str):
            continue
        shortened = truncate_text(message, max_chars)
        if shortened != message:
            item["message"] = shortened
            changed = True
    return changed


def build_summary(
    run: NormalizedRun,
    *,
    cursor: str | None = None,
    budget: int = DEFAULT_BUDGET,
    page_size: int = 10,
) -> SummaryPayload:
    message_truncated = False
    budget_truncated = False
    offset = decode_cursor(cursor)
    size = _clamp_page_size(page_size, default=10)
    failed_nodes = run.failed_tests
    page_nodes = failed_nodes[offset : offset + size]
    next_cursor = (
        encode_cursor(offset + len(page_nodes))
        if offset + len(page_nodes) < len(failed_nodes)
        else None
    )
    failed_tests = []
    for node in page_nodes:
        shortened = truncate_text(node.message, 320)
        if shortened != node.message:
            message_truncated = True
        failed_tests.append(
            {
                "test_id": node.id,
                "name": node.name,
                "longname": node.longname,
                "status": node.status,
                "message": shortened,
                "ref_uri": node.ref_uri,
            }
        )
    errors = []
    for item in run.errors[:10]:
        shortened = truncate_text(item.message, 320)
        if shortened != item.message:
            message_truncated = True
        errors.append(
            {
                "error_id": item.id,
                "level": item.level,
                "message": shortened,
                "ref_uri": item.ref_uri,
            }
        )
    page_truncated = next_cursor is not None
    payload = SummaryPayload(
        input_profile=run.metadata.input_profile,
        run_id=run.run_id,
        estimated_tokens=0,
        truncated=message_truncated or budget_truncated or page_truncated,
        message_truncated=message_truncated,
        budget_truncated=budget_truncated,
        page_truncated=page_truncated,
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
        errors=errors,
        next_cursor=next_cursor,
    )
    payload.estimated_tokens = estimate_tokens(payload.model_dump())
    if payload.estimated_tokens > budget:
        budget_truncated = True
        for max_chars in (160, 80, 40):
            failed_messages_truncated = _shrink_messages(payload.failed_tests, max_chars)
            error_messages_truncated = _shrink_messages(payload.errors, max_chars)
            message_truncated = (
                failed_messages_truncated or error_messages_truncated or message_truncated
            )
            payload.estimated_tokens = estimate_tokens(payload.model_dump())
            if payload.estimated_tokens <= budget:
                break
        while payload.estimated_tokens > budget and (
            len(payload.failed_tests) > 1 or len(payload.errors) > 1
        ):
            if len(payload.failed_tests) >= len(payload.errors) and len(payload.failed_tests) > 1:
                payload.failed_tests = payload.failed_tests[
                    : max(1, len(payload.failed_tests) // 2)
                ]
            elif len(payload.errors) > 1:
                payload.errors = payload.errors[: max(1, len(payload.errors) // 2)]
            payload.estimated_tokens = estimate_tokens(payload.model_dump())
        payload.next_cursor = (
            encode_cursor(offset + len(payload.failed_tests))
            if offset + len(payload.failed_tests) < len(failed_nodes)
            else None
        )
        payload.page_truncated = payload.next_cursor is not None
        payload.budget_truncated = True
        payload.message_truncated = message_truncated
        payload.truncated = (
            payload.message_truncated or payload.budget_truncated or payload.page_truncated
        )
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


def _branch_severity(
    branch: list[NodeRecord],
    messages_lookup: dict[str | None, list[MessageRecord]],
) -> int:
    severity = 0
    for node in branch:
        if (node.status or "").upper() == "FAIL" and node.message:
            severity = max(severity, _level_severity("FAIL"))
        for message in messages_lookup.get(node.id, []):
            severity = max(severity, _level_severity(message.level))
    return severity


def _best_failed_branch(
    test_node: NodeRecord,
    children: dict[str | None, list[NodeRecord]],
    messages_lookup: dict[str | None, list[MessageRecord]],
) -> list[NodeRecord]:
    best_branch: list[NodeRecord] | None = None
    best_score: tuple[int, int, tuple[int, ...]] | None = None

    def score(branch: list[NodeRecord]) -> tuple[int, int, tuple[int, ...]]:
        return (
            len(branch),
            -_branch_severity(branch, messages_lookup),
            tuple(node.sequence for node in branch),
        )

    def visit(node: NodeRecord, path: list[NodeRecord]) -> None:
        nonlocal best_branch, best_score
        failed_children = [
            child for child in children.get(node.id, []) if (child.status or "").upper() == "FAIL"
        ]
        if not failed_children:
            branch_score = score(path)
            if best_score is None or branch_score < best_score:
                best_branch = list(path)
                best_score = branch_score
            return
        for child in failed_children:
            path.append(child)
            visit(child, path)
            path.pop()

    visit(test_node, [test_node])
    return best_branch or [test_node]


def build_failure_path(
    run: NormalizedRun,
    *,
    selector: str | None,
    budget: int = DEFAULT_BUDGET,
) -> FailurePathPayload:
    children = _children_lookup(run)
    messages_lookup = _messages_by_parent(run)
    test_node = _find_test(run, selector)
    chain = _best_failed_branch(test_node, children, messages_lookup)
    seen_messages: set[str] = set()
    key_messages: list[dict[str, Any]] = []
    message_truncated = False
    budget_truncated = False
    for node in chain:
        for message in messages_lookup.get(node.id, []):
            normalized = message.message.strip()
            if not normalized or normalized in seen_messages:
                continue
            seen_messages.add(normalized)
            shortened = truncate_text(message.message, 360)
            if shortened != message.message:
                message_truncated = True
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
            message_truncated = True
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
        truncated=message_truncated or budget_truncated,
        message_truncated=message_truncated,
        budget_truncated=budget_truncated,
        page_truncated=False,
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
        for max_chars in (180, 90, 45):
            message_truncated = (
                _shrink_messages(payload.key_messages, max_chars) or message_truncated
            )
            payload.estimated_tokens = estimate_tokens(payload.model_dump())
            if payload.estimated_tokens <= budget:
                break
        while payload.estimated_tokens > budget and len(payload.key_messages) > 1:
            payload.key_messages = payload.key_messages[: max(1, len(payload.key_messages) // 2)]
            payload.estimated_tokens = estimate_tokens(payload.model_dump())
        payload.budget_truncated = True
        payload.message_truncated = message_truncated
        payload.truncated = (
            payload.message_truncated or payload.budget_truncated or payload.page_truncated
        )
        payload.estimated_tokens = estimate_tokens(payload.model_dump())
    return payload


def _find_node(run: NormalizedRun, selector: str) -> NodeRecord:
    try:
        return _node_lookup(run)[selector]
    except KeyError as exc:
        raise TestNotFoundError(selector) from exc


def build_step_window(
    run: NormalizedRun,
    *,
    selector: str,
    cursor: str | None,
    budget: int = DEFAULT_BUDGET,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> StepWindowPayload:
    selected_node = _find_node(run, selector)
    test_node = (
        selected_node
        if selected_node.kind == "TEST"
        else _find_test(run, selected_node.owner_test_id)
    )
    offset = decode_cursor(cursor)
    size = _clamp_page_size(page_size, default=DEFAULT_PAGE_SIZE)
    items: list[dict[str, Any]] = []
    message_truncated = False
    budget_truncated = False
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
        shortened = truncate_text(message.message, 240)
        if shortened != message.message:
            message_truncated = True
        items.append(
            {
                "kind": "message",
                "message_id": message.id,
                "level": message.level,
                "message": shortened,
                "sequence": message.sequence,
                "ref_uri": message.ref_uri,
            }
        )
    items.sort(key=lambda item: item["sequence"])
    if cursor is None and selected_node.id != test_node.id:
        selected_index = next(
            (
                index
                for index, item in enumerate(items)
                if item.get("kind") == "node" and item.get("node_id") == selected_node.id
            ),
            0,
        )
        offset = max(0, selected_index - size // 2)
    page = items[offset : offset + size]
    next_cursor = encode_cursor(offset + size) if offset + size < len(items) else None
    page_truncated = next_cursor is not None
    payload = StepWindowPayload(
        input_profile=run.metadata.input_profile,
        run_id=run.run_id,
        estimated_tokens=0,
        truncated=message_truncated or budget_truncated or page_truncated,
        message_truncated=message_truncated,
        budget_truncated=budget_truncated,
        page_truncated=page_truncated,
        test_id=test_node.id,
        test_name=test_node.longname or test_node.name,
        selected_node_id=selected_node.id,
        selected_node_name=selected_node.longname or selected_node.name,
        items=page,
        next_cursor=next_cursor,
    )
    payload.estimated_tokens = estimate_tokens(payload.model_dump())
    if payload.estimated_tokens > budget:
        for max_chars in (120, 60, 30):
            message_truncated = _shrink_messages(payload.items, max_chars) or message_truncated
            payload.estimated_tokens = estimate_tokens(payload.model_dump())
            if payload.estimated_tokens <= budget:
                break
        while payload.estimated_tokens > budget and len(payload.items) > 1:
            payload.items = payload.items[: max(1, len(payload.items) // 2)]
            payload.estimated_tokens = estimate_tokens(payload.model_dump())
        payload.next_cursor = (
            encode_cursor(offset + len(payload.items))
            if offset + len(payload.items) < len(items)
            else None
        )
        payload.budget_truncated = True
        payload.page_truncated = payload.next_cursor is not None
        payload.message_truncated = message_truncated
        payload.truncated = (
            payload.message_truncated or payload.budget_truncated or payload.page_truncated
        )
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
        truncated=False,
        message_truncated=False,
        budget_truncated=False,
        page_truncated=has_more,
        query=query,
        level=level,
        results=[],
        next_cursor=encode_cursor(offset + len(results)) if has_more else None,
    )
    for item in results:
        shortened = truncate_text(item["message"], 240)
        if shortened != item["message"]:
            payload.message_truncated = True
        payload.results.append(
            {
                "message_id": item["message_id"],
                "owner_test_id": item["owner_test_id"],
                "node_id": item["node_id"],
                "level": item["level"],
                "message": shortened,
                "timestamp": item["timestamp"],
                "ref_uri": item["ref_uri"],
            }
        )
    payload.truncated = (
        payload.message_truncated or payload.budget_truncated or payload.page_truncated
    )
    payload.estimated_tokens = estimate_tokens(payload.model_dump())
    return payload
