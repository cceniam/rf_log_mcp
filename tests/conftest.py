from __future__ import annotations

from pathlib import Path

import pytest

from rf_log_mcp.server.app import RfLogService
from rf_log_mcp.storage.sqlite_store import RunStore


@pytest.fixture
def service(tmp_path: Path) -> RfLogService:
    return RfLogService(RunStore(tmp_path / "store.sqlite3"))
