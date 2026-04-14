from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Debug helper for rf-log-mcp service methods without starting stdio transport."
    )
    parser.add_argument(
        "--fixture",
        default="tests/fixtures/single_failure_611.xml",
        help="Path to a Robot Framework output.xml or RF 7.2+ output.json fixture.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Optional SQLite file used for local debugging. Defaults to a per-fixture debug DB.",
    )
    parser.add_argument(
        "--action",
        choices=["parse", "summary", "failure_path", "step_window", "search"],
        default="summary",
        help="Service action to execute.",
    )
    parser.add_argument(
        "--selector",
        default=None,
        help="Test selector for failure_path / step_window. Example: s1-t1",
    )
    parser.add_argument(
        "--cursor",
        default=None,
        help="Cursor for paginated step_window or search calls.",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=1200,
        help="Budget passed to get_view.",
    )
    parser.add_argument(
        "--query",
        default="collected line",
        help="Search query used when --action search.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Search limit used when --action search.",
    )
    return parser


def default_db_path_for(fixture_path: Path) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", fixture_path.stem).strip("-") or "debug"
    return ROOT / ".rf_log_mcp" / f"{slug}.sqlite3"


def main() -> None:
    from rf_log_mcp.server.app import RfLogService
    from rf_log_mcp.storage.sqlite_store import RunStore

    args = build_parser().parse_args()

    fixture_path = (ROOT / args.fixture).resolve()
    db_path = (ROOT / args.db).resolve() if args.db else default_db_path_for(fixture_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    service = RfLogService(RunStore(db_path))
    parsed = service.parse_result(str(fixture_path))

    if args.action == "parse":
        result = parsed
    elif args.action == "summary":
        result = service.get_view(parsed["run_id"], view="summary", budget=args.budget)
    elif args.action == "failure_path":
        result = service.get_view(
            parsed["run_id"],
            view="failure_path",
            selector=args.selector,
            budget=args.budget,
        )
    elif args.action == "step_window":
        selector = args.selector or "s1-t1"
        result = service.get_view(
            parsed["run_id"],
            view="step_window",
            selector=selector,
            cursor=args.cursor,
            budget=args.budget,
        )
    else:
        result = service.search_messages(
            parsed["run_id"],
            query=args.query,
            limit=args.limit,
            cursor=args.cursor,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
