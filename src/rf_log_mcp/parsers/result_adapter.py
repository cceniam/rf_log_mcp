"""Robot Framework result parsing shared by XML and JSON inputs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from robot.api import ExecutionResult, ResultVisitor
from robot.errors import DataError

from rf_log_mcp.domain.models import (
    ErrorRecord,
    MessageRecord,
    NodeRecord,
    NormalizedRun,
    RunMetadata,
)
from rf_log_mcp.errors import InvalidJsonError, InvalidXmlError
from rf_log_mcp.parsers.gating import ProbedInput, sha256_file

_DEPRECATED_CONTROL_FLOW_CLASSES = {
    "Break",
    "Continue",
    "For",
    "ForIteration",
    "IfBranch",
    "Return",
}


def _model_class_name(model: Any) -> str:
    return model.__class__.__name__


def _uses_deprecated_keyword_metadata(model: Any) -> bool:
    return _model_class_name(model) in _DEPRECATED_CONTROL_FLOW_CLASSES


def _ref_uri(run_id: int | str, node_id: str) -> str:
    return f"rf://runs/{run_id}/nodes/{node_id}"


def _node_name(model: Any) -> str:
    class_name = _model_class_name(model)
    if class_name == "IfBranch":
        return f"IF {condition}" if (condition := getattr(model, "condition", None)) else "IF"
    if class_name == "Return":
        return "RETURN"
    if class_name == "For":
        return "FOR"
    if class_name == "ForIteration":
        return "FOR ITERATION"
    if class_name == "Break":
        return "BREAK"
    if class_name == "Continue":
        return "CONTINUE"
    return (
        getattr(model, "kwname", None)
        or getattr(model, "name", None)
        or getattr(model, "type", None)
        or model.__class__.__name__
    )


def _node_longname(model: Any) -> str | None:
    return getattr(model, "longname", None) or getattr(model, "full_name", None)


def _node_libname(model: Any) -> str | None:
    if _uses_deprecated_keyword_metadata(model):
        return None
    return getattr(model, "libname", None)


def _node_tags(model: Any) -> list[str]:
    if _uses_deprecated_keyword_metadata(model):
        return []
    return list(getattr(model, "tags", []) or [])


def _owner_test_id(model: Any) -> str | None:
    current = model
    while current is not None:
        if getattr(current, "type", None) == "TEST":
            return getattr(current, "id", None)
        current = getattr(current, "parent", None)
    return None


def _elapsed_ms(model: Any) -> float | None:
    elapsed = getattr(model, "elapsed_time", None)
    if elapsed is None:
        return None
    try:
        return float(elapsed.total_seconds() * 1000)
    except AttributeError:
        return None


class _ResultCollector(ResultVisitor):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.sequence = 0
        self.nodes: list[NodeRecord] = []
        self.messages: list[MessageRecord] = []

    def _next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def _add_node(self, model: Any, *, kind: str | None = None) -> None:
        node_id = getattr(model, "id", None)
        if not node_id:
            return
        parent = getattr(model, "parent", None)
        parent_id = getattr(parent, "id", None)
        self.nodes.append(
            NodeRecord(
                id=node_id,
                parent_id=parent_id,
                owner_test_id=_owner_test_id(model),
                kind=kind or getattr(model, "type", model.__class__.__name__),
                name=_node_name(model),
                longname=_node_longname(model),
                status=getattr(model, "status", None),
                message=getattr(model, "message", None),
                keyword_type=getattr(model, "type", None),
                libname=_node_libname(model),
                start_time=_stringify_time(getattr(model, "start_time", None)),
                end_time=_stringify_time(getattr(model, "end_time", None)),
                elapsed_ms=_elapsed_ms(model),
                tags=_node_tags(model),
                sequence=self._next_sequence(),
                ref_uri=_ref_uri(self.run_id, node_id),
            )
        )

    def _add_message(self, model: Any) -> None:
        message_id = getattr(model, "id", None)
        if not message_id:
            return
        parent = getattr(model, "parent", None)
        parent_id = getattr(parent, "id", None)
        self.messages.append(
            MessageRecord(
                id=message_id,
                parent_id=parent_id,
                owner_test_id=_owner_test_id(model),
                level=getattr(model, "level", "INFO"),
                message=getattr(model, "message", ""),
                timestamp=_stringify_time(getattr(model, "timestamp", None)),
                html=bool(getattr(model, "html", False)),
                sequence=self._next_sequence(),
                ref_uri=_ref_uri(self.run_id, message_id),
            )
        )

    def start_suite(self, suite: Any) -> None:
        self._add_node(suite, kind="SUITE")

    def start_test(self, test: Any) -> None:
        self._add_node(test, kind="TEST")

    def start_keyword(self, keyword: Any) -> None:
        self._add_node(keyword, kind="KEYWORD")

    def start_for(self, node: Any) -> None:
        self._add_node(node)

    def start_for_iteration(self, node: Any) -> None:
        self._add_node(node)

    def start_if(self, node: Any) -> None:
        self._add_node(node)

    def start_if_branch(self, node: Any) -> None:
        self._add_node(node)

    def start_try(self, node: Any) -> None:
        self._add_node(node)

    def start_try_branch(self, node: Any) -> None:
        self._add_node(node)

    def start_while(self, node: Any) -> None:
        self._add_node(node)

    def start_while_iteration(self, node: Any) -> None:
        self._add_node(node)

    def start_group(self, node: Any) -> None:
        self._add_node(node)

    def start_break(self, node: Any) -> None:
        self._add_node(node)

    def start_continue(self, node: Any) -> None:
        self._add_node(node)

    def start_return(self, node: Any) -> None:
        self._add_node(node)

    def start_var(self, node: Any) -> None:
        self._add_node(node)

    def start_message(self, message: Any) -> None:
        self._add_message(message)


def _stringify_time(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _collect_errors(run_id: str, errors: Iterable[Any]) -> list[ErrorRecord]:
    records: list[ErrorRecord] = []
    for item in errors:
        item_id = getattr(item, "id", None) or f"error-{len(records) + 1}"
        records.append(
            ErrorRecord(
                id=item_id,
                level=getattr(item, "level", "ERROR"),
                message=getattr(item, "message", ""),
                timestamp=_stringify_time(getattr(item, "timestamp", None)),
                ref_uri=_ref_uri(run_id, item_id),
            )
        )
    return records


def parse_output_result(probed: ProbedInput) -> NormalizedRun:
    content_hash = sha256_file(probed.path)
    try:
        result = ExecutionResult(str(probed.path))
    except DataError as exc:
        if probed.source_format == "json":
            raise InvalidJsonError(str(exc)) from exc
        raise InvalidXmlError(str(exc)) from exc

    collector = _ResultCollector(content_hash)
    result.visit(collector)
    metadata = RunMetadata(
        source_path=str(probed.path),
        source_name=probed.path.name,
        source_format=probed.source_format,
        generator=result.generator or probed.generator,
        generated=probed.generated,
        generation_time=_stringify_time(getattr(result, "generation_time", None)),
        rpa=probed.rpa if probed.rpa is not None else getattr(result, "rpa", None),
        schemaversion=probed.schemaversion,
        input_profile=probed.input_profile,
    )
    return NormalizedRun(
        run_id=None,
        content_hash=content_hash,
        metadata=metadata,
        statistics=result.statistics.to_dict(),
        nodes=collector.nodes,
        messages=collector.messages,
        errors=_collect_errors(content_hash, result.errors),
    )
