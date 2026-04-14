from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from rf_log_mcp.server import app as app_module
from tests.helpers import fixture_path


def test_mcp_tools_are_registered() -> None:
    async def _tool_names() -> set[str]:
        tools = await app_module.mcp.list_tools()
        return {tool.name for tool in tools}

    assert {"parse_result", "get_view", "search_messages"} <= asyncio.run(_tool_names())


def test_mcp_tool_call_and_resource(monkeypatch, tmp_path) -> None:
    service = app_module.RfLogService(app_module.RunStore(tmp_path / "store.sqlite3"))
    monkeypatch.setattr(app_module, "SERVICE", service)

    async def _exercise() -> None:
        _, parsed = await app_module.mcp.call_tool(
            "parse_result",
            {"path": str(fixture_path("single_failure_611.xml"))},
        )
        assert parsed["ok"] is True
        _, summary = await app_module.mcp.call_tool(
            "get_view",
            {"run_id": parsed["run_id"], "view": "summary"},
        )
        assert summary["ok"] is True
        resource = await app_module.mcp.read_resource(
            f"rf://runs/{parsed['run_id']}/summary"
        )
        assert resource
        _, parsed_json = await app_module.mcp.call_tool(
            "parse_result",
            {"path": str(fixture_path("single_failure_72.json"))},
        )
        assert parsed_json["ok"] is True
        assert parsed_json["source_format"] == "json"

    asyncio.run(_exercise())


def test_logging_uses_stderr() -> None:
    command = (
        "from rf_log_mcp.server.app import configure_logging; "
        "import logging; "
        "configure_logging(); "
        "logging.getLogger('rf_log_mcp').info('hello from logger')"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.stdout == ""
    assert "hello from logger" in completed.stderr
