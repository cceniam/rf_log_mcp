"""Dataclass-based normalized domain model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RunMetadata:
    source_path: str
    source_name: str
    source_format: str
    generator: str
    generated: str | None
    generation_time: str | None
    rpa: bool | None
    schemaversion: int | None
    input_profile: str


@dataclass(slots=True)
class NodeRecord:
    id: str
    parent_id: str | None
    owner_test_id: str | None
    kind: str
    name: str
    longname: str | None
    status: str | None
    message: str | None
    keyword_type: str | None
    libname: str | None
    start_time: str | None
    end_time: str | None
    elapsed_ms: float | None
    tags: list[str] = field(default_factory=list)
    sequence: int = 0
    ref_uri: str = ""


@dataclass(slots=True)
class MessageRecord:
    id: str
    parent_id: str | None
    owner_test_id: str | None
    level: str
    message: str
    timestamp: str | None
    html: bool
    sequence: int
    ref_uri: str


@dataclass(slots=True)
class ErrorRecord:
    id: str
    level: str
    message: str
    timestamp: str | None
    ref_uri: str


@dataclass(slots=True)
class NormalizedRun:
    run_id: int | None
    content_hash: str
    metadata: RunMetadata
    statistics: dict[str, Any]
    nodes: list[NodeRecord]
    messages: list[MessageRecord]
    errors: list[ErrorRecord]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedRun:
        metadata = dict(data["metadata"])
        metadata.setdefault("source_name", "")
        metadata.setdefault("source_format", "xml")
        metadata.setdefault("schemaversion", None)
        run_id = data["run_id"]
        content_hash = data.get("content_hash")
        if content_hash is None and isinstance(run_id, str):
            content_hash = run_id
            run_id = None
        return cls(
            run_id=run_id,
            content_hash=content_hash or "",
            metadata=RunMetadata(**metadata),
            statistics=data["statistics"],
            nodes=[NodeRecord(**item) for item in data["nodes"]],
            messages=[MessageRecord(**item) for item in data["messages"]],
            errors=[ErrorRecord(**item) for item in data["errors"]],
        )

    @property
    def test_nodes(self) -> list[NodeRecord]:
        return [node for node in self.nodes if node.kind == "TEST"]

    @property
    def failed_tests(self) -> list[NodeRecord]:
        return [node for node in self.test_nodes if (node.status or "").upper() == "FAIL"]
