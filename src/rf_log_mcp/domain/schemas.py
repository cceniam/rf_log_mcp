"""Pydantic schemas used at MCP boundaries."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from rf_log_mcp.constants import DEFAULT_INPUT_PROFILE, SCHEMA_VERSION


class ErrorPayload(BaseModel):
    schema_version: str = SCHEMA_VERSION
    ok: bool = False
    error_code: str
    error_message: str
    input_profile: str = DEFAULT_INPUT_PROFILE


class BasePayload(BaseModel):
    schema_version: str = SCHEMA_VERSION
    ok: bool = True
    input_profile: str
    run_id: int
    estimated_tokens: int
    truncated: bool
    message_truncated: bool = False
    budget_truncated: bool = False
    page_truncated: bool = False


class ParseResultPayload(BasePayload):
    source_format: str
    source_path: str
    generator: str
    generated: str | None
    schemaversion: int | None
    cached: bool
    available_views: list[str]
    resource_uris: list[str]


class SummaryPayload(BasePayload):
    metadata: dict[str, Any]
    statistics: dict[str, Any]
    failed_tests: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    next_cursor: str | None = None


class FailurePathPayload(BasePayload):
    selected_test_id: str
    selected_test_name: str
    failure_chain: list[dict[str, Any]]
    key_messages: list[dict[str, Any]]


class StepWindowPayload(BasePayload):
    test_id: str
    test_name: str
    selected_node_id: str | None = None
    selected_node_name: str | None = None
    items: list[dict[str, Any]]
    next_cursor: str | None = None


class SearchMessagesPayload(BasePayload):
    query: str
    level: str | None = None
    results: list[dict[str, Any]]
    next_cursor: str | None = None


class TestResourcePayload(BaseModel):
    schema_version: str = SCHEMA_VERSION
    run_id: int
    input_profile: str
    test: dict[str, Any]
    failure_path: list[dict[str, Any]] = Field(default_factory=list)
