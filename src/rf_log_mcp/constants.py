"""Project-wide constants."""

from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = "1.0.0"
DEFAULT_INPUT_PROFILE = "rf-output-result"
XML_INPUT_PROFILE = "rf-output-xml"
JSON_INPUT_PROFILE = "rf-7.2+-output-json"
SUPPORTED_XML_SCHEMA_VERSIONS = (3, 4, 5)
MINIMUM_JSON_VERSION = (7, 2)
DEFAULT_BUDGET = 1200
DEFAULT_PAGE_SIZE = 25
DEFAULT_CACHE_SIZE = 8
DB_ENV_VAR = "RF_LOG_MCP_DB"


def default_db_path() -> Path:
    return Path.cwd() / ".rf_log_mcp" / "store.sqlite3"
