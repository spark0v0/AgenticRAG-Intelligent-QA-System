"""Transactional history with non-destructive, idempotent legacy JSON import."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class SessionMemory:
    def __init__(self, storage_path: str | Path):
        original = Path(storage_path)
        self.storage_path = original.with_suffix(".sqlite3") if original.suffix == ".json" else original
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    timestamp REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, timestamp);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL,
                    started_at REAL NOT NULL, finished_at REAL, query TEXT NOT NULL,
                    result TEXT, error TEXT
                );
                CREATE INDEX IF NOT EXISTS runs_session ON runs(session_id, started_at);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(session_id) WHERE status='running';
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL, seq INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS migrations (id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, run_id TEXT,
                    role TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id);
            """)
        if original.suffix == ".json" and original.exists():
            self._import_json(original)
        with self.connect() as db:
            for row in db.execute("SELECT * FROM turns").fetchall():
                self._save_messages(db, row["id"], row["session_id"], json.loads(row["payload"]))

    def _save_messages(self, db, identity: str, session_id: str, turn: dict) -> None:
        db.execute("INSERT OR IGNORE INTO sessions VALUES(?,?)", (session_id, turn.get("timestamp") or time.time()))
        for role, content in (("user", turn.get("query", "")), ("assistant", turn.get("response", ""))):
            payload = {"content": content, "attachments": turn.get("attachments", [])} if role == "user" else {"content": content, "result": turn.get("result")}
            db.execute("INSERT OR REPLACE INTO messages VALUES(?,?,?,?,?)", (
                f"{identity}-{role}", session_id, turn.get("run_id"), role, json.dumps(payload, ensure_ascii=False)))

    def save_input(self, run_id: str, session_id: str, query: str, attachments: list) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO messages VALUES(?,?,?,?,?)", (
                f"{run_id}-user", session_id, run_id, "user",
                json.dumps({"content": query, "attachments": attachments}, ensure_ascii=False)))

    def complete_run(self, run_id: str, result: dict, turn: dict) -> None:
        # Commit the final answer, metadata and terminal status together.
        with self.connect() as db:
            row = db.execute("SELECT session_id FROM runs WHERE id=? AND status='running'", (run_id,)).fetchone()
            if row is None:
                raise ValueError("本轮已结束，不能重复保存回答")
            session_id = row[0]
            db.execute("INSERT INTO turns VALUES(?,?,?,?)", (run_id, session_id, turn["timestamp"], json.dumps(turn, ensure_ascii=False)))
            self._save_messages(db, run_id, session_id, turn)
            db.execute("UPDATE runs SET status='success',finished_at=?,result=? WHERE id=?", (
                time.time(), json.dumps(result, ensure_ascii=False), run_id))

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.storage_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _import_json(self, path: Path) -> None:
        migration = "legacy:" + str(path.resolve())
        with self.connect() as db:
            if db.execute("SELECT 1 FROM migrations WHERE id=?", (migration,)).fetchone():
                return
            sessions = json.loads(path.read_text(encoding="utf-8"))
            for session, turns in sessions.items():
                for index, turn in enumerate(turns):
                    identity = hashlib.sha256(f"{migration}:{session}:{index}".encode()).hexdigest()
                    db.execute("INSERT OR IGNORE INTO turns VALUES(?,?,?,?)", (
                        identity, session, turn.get("timestamp") or 0, json.dumps(turn, ensure_ascii=False)))
            db.execute("INSERT OR IGNORE INTO migrations VALUES(?)", (migration,))

    def get_history(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.get_session(session_id)[-limit:]

    def get_session(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM turns WHERE session_id=? ORDER BY timestamp, rowid", (session_id,))
            return [json.loads(row[0]) for row in rows]

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            ids = db.execute("""SELECT session_id, MAX(timestamp) updated_at FROM (
                SELECT session_id, timestamp FROM turns UNION ALL
                SELECT session_id, started_at AS timestamp FROM runs
            ) GROUP BY session_id ORDER BY updated_at DESC""").fetchall()
        result = []
        for row in ids:
            turns = self.get_session(row["session_id"])
            runs = self.list_runs(row["session_id"])
            result.append({"session_id": row["session_id"], "updated_at": row["updated_at"],
                           "turn_count": len(turns), "preview": (turns[-1]["query"] if turns else runs[-1]["query"])[:80]})
        return result

    def append_turn(self, session_id: str, turn: dict[str, Any], limit: int = 20) -> None:
        # Only model context is truncated, never the persistent history.
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO turns VALUES(?,?,?,?)", (
                turn.get("run_id") or str(uuid.uuid4()), session_id,
                turn.get("timestamp") or time.time(), json.dumps(turn, ensure_ascii=False)))

    def start_run(self, run_id: str, session_id: str, query: str) -> None:
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO sessions VALUES(?,?)", (session_id, time.time()))
            db.execute("INSERT INTO runs(id,session_id,status,started_at,query) VALUES(?,?,'running',?,?)",
                       (run_id, session_id, time.time(), query))

    def finish_run(self, run_id: str, status: str, result: dict | None = None, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute("UPDATE runs SET status=?, finished_at=?, result=?, error=? WHERE id=? AND status='running'",
                       (status, time.time(), json.dumps(result, ensure_ascii=False) if result else None, error, run_id))

    def recover_interrupted_runs(self) -> None:
        # Single-worker service; call once on application startup, never per query.
        with self.connect() as db:
            db.execute("UPDATE runs SET status='error', finished_at=?, error='服务重启，本轮执行已中断' WHERE status='running'", (time.time(),))

    def record_event(self, event: dict) -> None:
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?)", (
                event["run_id"], event["seq"], json.dumps(event, ensure_ascii=False)))

    def get_events(self, session_id: str, run_id: str | None = None) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""SELECT e.payload FROM events e JOIN runs r ON r.id=e.run_id
                WHERE r.session_id=? AND (? IS NULL OR r.id=?) ORDER BY r.started_at,e.seq""",
                              (session_id, run_id, run_id))
            return [json.loads(row[0]) for row in rows]

    def list_runs(self, session_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM runs WHERE session_id=? ORDER BY started_at", (session_id,)).fetchall()
            inputs = {row["run_id"]: json.loads(row["payload"]) for row in db.execute(
                "SELECT run_id,payload FROM messages WHERE session_id=? AND role='user'", (session_id,))}
        return [{**dict(row), "attachments": inputs.get(row["id"], {}).get("attachments", []),
                 "result": json.loads(row["result"]) if row["result"] else None} for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT status,result,error FROM runs WHERE id=?", (run_id,)).fetchone()
        return {**dict(row), "result": json.loads(row["result"]) if row["result"] else None} if row else None
