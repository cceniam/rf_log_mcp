"""SQLite-backed storage with a small in-memory LRU cache."""

from __future__ import annotations

import json
import sqlite3
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Any

from rf_log_mcp.constants import DEFAULT_CACHE_SIZE
from rf_log_mcp.domain.models import NormalizedRun
from rf_log_mcp.errors import RunNotFoundError
from rf_log_mcp.parsers.gating import sha256_file


class RunStore:
    def __init__(self, db_path: Path, cache_size: int = DEFAULT_CACHE_SIZE) -> None:
        self.db_path = db_path
        self.cache_size = cache_size
        self._cache: OrderedDict[int, NormalizedRun] = OrderedDict()
        self._lock = RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            self._migrate_legacy_schema(connection)
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT NOT NULL UNIQUE,
                    input_profile TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_format TEXT NOT NULL,
                    generator TEXT NOT NULL,
                    generated TEXT,
                    schemaversion INTEGER,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tests (
                    run_id INTEGER NOT NULL,
                    test_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    longname TEXT NOT NULL,
                    status TEXT,
                    message TEXT,
                    tags_json TEXT NOT NULL,
                    ref_uri TEXT NOT NULL,
                    PRIMARY KEY (run_id, test_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    run_id INTEGER NOT NULL,
                    message_id TEXT NOT NULL,
                    owner_test_id TEXT,
                    node_id TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT,
                    sequence INTEGER NOT NULL,
                    ref_uri TEXT NOT NULL,
                    PRIMARY KEY (run_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS view_cache (
                    run_id INTEGER NOT NULL,
                    view_name TEXT NOT NULL,
                    selector TEXT NOT NULL,
                    budget INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, view_name, selector, budget)
                );
                """
            )

    def _migrate_legacy_schema(self, connection: sqlite3.Connection) -> None:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "runs" not in tables:
            return

        run_columns = connection.execute("PRAGMA table_info(runs)").fetchall()
        column_names = {column["name"] for column in run_columns}
        if "id" in column_names and "content_hash" in column_names:
            return

        connection.executescript(
            """
            ALTER TABLE runs RENAME TO runs_old;

            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL UNIQUE,
                input_profile TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_format TEXT NOT NULL,
                generator TEXT NOT NULL,
                generated TEXT,
                schemaversion INTEGER,
                payload_json TEXT NOT NULL
            );

            INSERT INTO runs (
                content_hash,
                input_profile,
                source_path,
                source_name,
                source_format,
                generator,
                generated,
                schemaversion,
                payload_json
            )
            SELECT
                run_id,
                input_profile,
                source_path,
                source_path,
                CASE
                    WHEN lower(source_path) LIKE '%.json' OR lower(input_profile) LIKE '%json%'
                    THEN 'json'
                    ELSE 'xml'
                END,
                generator,
                generated,
                schemaversion,
                payload_json
            FROM runs_old;
            """
        )

        if "tests" in tables:
            connection.executescript(
                """
                ALTER TABLE tests RENAME TO tests_old;

                CREATE TABLE tests (
                    run_id INTEGER NOT NULL,
                    test_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    longname TEXT NOT NULL,
                    status TEXT,
                    message TEXT,
                    tags_json TEXT NOT NULL,
                    ref_uri TEXT NOT NULL,
                    PRIMARY KEY (run_id, test_id)
                );

                INSERT INTO tests (
                    run_id, test_id, name, longname, status, message, tags_json, ref_uri
                )
                SELECT
                    runs.id, tests_old.test_id, tests_old.name, tests_old.longname,
                    tests_old.status, tests_old.message, tests_old.tags_json, tests_old.ref_uri
                FROM tests_old
                JOIN runs ON runs.content_hash = tests_old.run_id;

                DROP TABLE tests_old;
                """
            )

        if "messages" in tables:
            connection.executescript(
                """
                ALTER TABLE messages RENAME TO messages_old;

                CREATE TABLE messages (
                    run_id INTEGER NOT NULL,
                    message_id TEXT NOT NULL,
                    owner_test_id TEXT,
                    node_id TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT,
                    sequence INTEGER NOT NULL,
                    ref_uri TEXT NOT NULL,
                    PRIMARY KEY (run_id, message_id)
                );

                INSERT INTO messages (
                    run_id,
                    message_id,
                    owner_test_id,
                    node_id,
                    level,
                    message,
                    timestamp,
                    sequence,
                    ref_uri
                )
                SELECT
                    runs.id,
                    messages_old.message_id,
                    messages_old.owner_test_id,
                    messages_old.node_id,
                    messages_old.level,
                    messages_old.message,
                    messages_old.timestamp,
                    messages_old.sequence,
                    messages_old.ref_uri
                FROM messages_old
                JOIN runs ON runs.content_hash = messages_old.run_id;

                DROP TABLE messages_old;
                """
            )

        if "view_cache" in tables:
            connection.executescript(
                """
                DROP TABLE view_cache;
                """
            )

        connection.execute("DROP TABLE runs_old")

    def get_run_id_by_hash(self, content_hash: str) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM runs WHERE content_hash = ? LIMIT 1",
                (content_hash,),
            ).fetchone()
        return int(row["id"]) if row is not None else None

    def resolve_run_ref(self, run_ref: int | str) -> int:
        if isinstance(run_ref, int):
            return run_ref
        if run_ref.isdigit():
            return int(run_ref)

        candidate = Path(run_ref).expanduser()
        if candidate.exists():
            content_hash = sha256_file(candidate.resolve())
            run_id = self.get_run_id_by_hash(content_hash)
            if run_id is not None:
                return run_id

        with self._connect() as connection:
            matches = connection.execute(
                "SELECT id FROM runs WHERE source_name = ? ORDER BY id DESC",
                (run_ref,),
            ).fetchall()
        if len(matches) == 1:
            return int(matches[0]["id"])
        raise RunNotFoundError(str(run_ref))

    def put_run(self, run: NormalizedRun, *, replace_existing: bool = False) -> int:
        existing_id = self.get_run_id_by_hash(run.content_hash)
        if existing_id is not None and not replace_existing:
            existing_run = self.get_run(existing_id)
            run.run_id = existing_run.run_id
            return existing_id

        with self._lock, self._connect() as connection:
            if existing_id is not None:
                run_id = existing_id
                connection.execute(
                    """
                    UPDATE runs
                    SET input_profile = ?,
                        source_path = ?,
                        source_name = ?,
                        source_format = ?,
                        generator = ?,
                        generated = ?,
                        schemaversion = ?
                    WHERE id = ?
                    """,
                    (
                        run.metadata.input_profile,
                        run.metadata.source_path,
                        run.metadata.source_name,
                        run.metadata.source_format,
                        run.metadata.generator,
                        run.metadata.generated,
                        run.metadata.schemaversion,
                        run_id,
                    ),
                )
                connection.execute("DELETE FROM tests WHERE run_id = ?", (run_id,))
                connection.execute("DELETE FROM messages WHERE run_id = ?", (run_id,))
                connection.execute("DELETE FROM view_cache WHERE run_id = ?", (run_id,))
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO runs (
                        content_hash,
                        input_profile,
                        source_path,
                        source_name,
                        source_format,
                        generator,
                        generated,
                        schemaversion,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.content_hash,
                        run.metadata.input_profile,
                        run.metadata.source_path,
                        run.metadata.source_name,
                        run.metadata.source_format,
                        run.metadata.generator,
                        run.metadata.generated,
                        run.metadata.schemaversion,
                        "",
                    ),
                )
                run_id = int(cursor.lastrowid)
            self._assign_run_identity(run, run_id)
            payload_json = json.dumps(run.to_dict(), ensure_ascii=False)
            connection.execute(
                "UPDATE runs SET payload_json = ? WHERE id = ?",
                (payload_json, run_id),
            )
            connection.executemany(
                """
                INSERT INTO tests (
                    run_id, test_id, name, longname, status, message, tags_json, ref_uri
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        node.id,
                        node.name,
                        node.longname or node.name,
                        node.status,
                        node.message,
                        json.dumps(node.tags, ensure_ascii=False),
                        node.ref_uri,
                    )
                    for node in run.test_nodes
                ],
            )
            connection.executemany(
                """
                INSERT INTO messages (
                    run_id,
                    message_id,
                    owner_test_id,
                    node_id,
                    level,
                    message,
                    timestamp,
                    sequence,
                    ref_uri
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        message.id,
                        message.owner_test_id,
                        message.parent_id,
                        message.level,
                        message.message,
                        message.timestamp,
                        message.sequence,
                        message.ref_uri,
                    )
                    for message in run.messages
                ],
            )
        self._remember(run)
        return run_id

    def get_run(self, run_id: int) -> NormalizedRun:
        with self._lock:
            cached = self._cache.get(run_id)
            if cached is not None:
                self._cache.move_to_end(run_id)
                return cached
        with self._connect() as connection:
            row = connection.execute(
                "SELECT content_hash, payload_json FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise RunNotFoundError(str(run_id))
        run = NormalizedRun.from_dict(json.loads(row["payload_json"]))
        run.content_hash = row["content_hash"]
        if not run.metadata.source_name:
            run.metadata.source_name = Path(run.metadata.source_path).name
        self._assign_run_identity(run, run_id)
        self._remember(run)
        return run

    def get_cached_view(
        self,
        run_id: int,
        view_name: str,
        selector: str | None,
        budget: int,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM view_cache
                WHERE run_id = ? AND view_name = ? AND selector = ? AND budget = ?
                """,
                (run_id, view_name, selector or "", budget),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        if not isinstance(payload.get("run_id"), int):
            return None
        return payload

    def set_cached_view(
        self,
        run_id: int,
        view_name: str,
        selector: str | None,
        budget: int,
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO view_cache (
                    run_id, view_name, selector, budget, payload_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    view_name,
                    selector or "",
                    budget,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def search_messages(
        self,
        run_id: int,
        query: str,
        *,
        level: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        sql = """
            SELECT message_id, owner_test_id, node_id, level, message, timestamp, sequence, ref_uri
            FROM messages
            WHERE run_id = ? AND message LIKE ?
        """
        params: list[Any] = [run_id, f"%{query}%"]
        if level:
            sql += " AND level = ?"
            params.append(level.upper())
        sql += " ORDER BY sequence ASC LIMIT ? OFFSET ?"
        params.extend([limit + 1, offset])
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        has_more = len(rows) > limit
        items = [dict(row) for row in rows[:limit]]
        return items, has_more

    def _assign_run_identity(self, run: NormalizedRun, run_id: int) -> None:
        run.run_id = run_id
        for node in run.nodes:
            node.ref_uri = self._ref_uri(run_id, node.id)
        for message in run.messages:
            message.ref_uri = self._ref_uri(run_id, message.id)
        for error in run.errors:
            error.ref_uri = self._ref_uri(run_id, error.id)

    def _remember(self, run: NormalizedRun) -> None:
        if run.run_id is None:
            return
        with self._lock:
            self._cache[run.run_id] = run
            self._cache.move_to_end(run.run_id)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

    @staticmethod
    def _ref_uri(run_id: int, node_id: str) -> str:
        return f"rf://runs/{run_id}/nodes/{node_id}"
