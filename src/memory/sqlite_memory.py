"""Transactional history with non-destructive, idempotent legacy JSON import."""
from __future__ import annotations
import hashlib
import base64
import json
import math
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
                CREATE INDEX IF NOT EXISTS runs_history_page ON runs(session_id, started_at, id);
                CREATE INDEX IF NOT EXISTS turns_history_page ON turns(session_id, timestamp, id);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(session_id) WHERE status='running';
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL, seq INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS migrations (id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS session_summaries (
                    session_id TEXT PRIMARY KEY, session_title TEXT NOT NULL,
                    preview TEXT NOT NULL, updated_at REAL NOT NULL,
                    turn_count INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS summary_order ON session_summaries(pinned DESC, updated_at DESC);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, run_id TEXT,
                    role TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id);
            """)
            # Additive migration: retain every existing run, including interrupted ones.
            db.execute("BEGIN IMMEDIATE")
            if "request" not in {row["name"] for row in db.execute("PRAGMA table_info(runs)")}:
                db.execute("ALTER TABLE runs ADD COLUMN request TEXT")
            db.execute("INSERT OR IGNORE INTO migrations VALUES('run-request-v1')")
        if original.suffix == ".json" and original.exists():
            self._import_json(original)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM migrations WHERE id='session-summary-v1'").fetchone():
                for row in db.execute("SELECT * FROM turns").fetchall():
                    self._save_messages(db, row["id"], row["session_id"], json.loads(row["payload"]))
                rows = db.execute("""SELECT session_id,timestamp,json_extract(payload,'$.query') AS query,1 AS count FROM turns
                    UNION ALL SELECT session_id,started_at,query,0 FROM runs
                    WHERE id NOT IN (SELECT id FROM turns) ORDER BY timestamp""").fetchall()
                for row in rows:
                    self._touch_summary(db, row["session_id"], row["query"] or "", row["timestamp"], row["count"])
                db.execute("INSERT INTO migrations VALUES('session-summary-v1')")

    @staticmethod
    def _touch_summary(db, session_id: str, query: str, timestamp: float, count: int = 0):
        title = query.strip()[:24] + ("..." if len(query.strip()) > 24 else "") or "图片问答"
        db.execute("""INSERT INTO session_summaries(session_id,session_title,preview,updated_at,turn_count)
            VALUES(?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET
            preview=CASE WHEN excluded.updated_at>=updated_at THEN excluded.preview ELSE preview END,
            updated_at=MAX(updated_at,excluded.updated_at),turn_count=turn_count+excluded.turn_count""",
            (session_id, title, query[:80], timestamp, count))

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
            self._touch_summary(db, session_id, turn.get("query", ""), turn["timestamp"], 1)
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
        if limit <= 0:
            return []
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM turns WHERE session_id=? ORDER BY timestamp DESC,rowid DESC LIMIT ?", (session_id, limit)).fetchall()
            return [json.loads(row[0]) for row in reversed(rows)]

    def get_session(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT id,payload FROM turns WHERE session_id=? ORDER BY timestamp, id", (session_id,))
            return [{**json.loads(row['payload']), '_history_id': row['id']} for row in rows]

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.search_sessions("", 0, None)["items"]

    def history_page(self, session_id: str, limit: int = 20, before: str | None = None) -> dict:
        """Page whole rounds, including failed runs and legacy turns, in one read snapshot."""
        if not 1 <= limit <= 50:
            raise ValueError("每页须为 1–50 轮")
        cursor = None
        if before:
            try:
                owner, stamp, kind, identity = json.loads(base64.urlsafe_b64decode(before.encode('ascii')))
                if (owner != session_id or type(stamp) not in (int, float) or not math.isfinite(stamp)
                        or type(kind) is not int or kind not in (0, 1)
                        or not isinstance(identity, str) or not 1 <= len(identity) <= 128):
                    raise ValueError()
                cursor = (stamp, kind, identity)
            except (ValueError, TypeError, UnicodeError) as exc:
                raise ValueError("历史分页游标无效，请重新打开会话") from exc
        with self.connect() as db:
            db.execute('BEGIN')
            # Only metadata is scanned; answers, attachments and events are read for this page.
            run_before = 'AND (started_at,1,id)<(?,?,?)' if cursor else ''
            turn_before = 'AND (timestamp,0,id)<(?,?,?)' if cursor else ''
            params = (session_id, *(cursor or ()), session_id, *(cursor or ()), limit + 1)
            rows = db.execute(f"""SELECT id,started_at AS stamp,1 AS kind FROM runs
                WHERE session_id=? {run_before}
                UNION ALL SELECT t.id,t.timestamp,0 FROM turns t WHERE session_id=? {turn_before}
                AND NOT EXISTS(SELECT 1 FROM runs r WHERE r.id=t.id)
                ORDER BY stamp DESC,kind DESC,id DESC LIMIT ?""", params).fetchall()
            has_more = len(rows) > limit
            rows = rows[:limit]
            turns, runs, events = [], [], []
            ids = [row['id'] for row in rows]
            if ids:
                placeholders = ','.join('?' for _ in ids)
                payloads = {row['id']: json.loads(row['payload']) for row in db.execute(
                    f'SELECT id,payload FROM turns WHERE session_id=? AND id IN ({placeholders})', (session_id, *ids))}
                run_rows = {row['id']: dict(row) for row in db.execute(
                    f'SELECT * FROM runs WHERE session_id=? AND id IN ({placeholders})', (session_id, *ids))}
                inputs = {row['run_id']: json.loads(row['payload']) for row in db.execute(
                    f"SELECT run_id,payload FROM messages WHERE session_id=? AND role='user' AND run_id IN ({placeholders})",
                    (session_id, *ids))}
                events = [json.loads(row[0]) for row in db.execute(f"""SELECT e.payload FROM events e
                    JOIN runs r ON r.id=e.run_id WHERE r.session_id=? AND r.id IN ({placeholders})
                    ORDER BY r.started_at,r.id,e.seq""", (session_id, *ids))]
                for row in reversed(rows):
                    identity = row['id']
                    if identity in payloads:
                        turns.append({**payloads[identity], 'timestamp': row['stamp'], '_history_id': identity})
                    if identity in run_rows:
                        run = run_rows[identity]
                        # Successful answer metadata is already on its message, not duplicated here.
                        run['result'] = json.loads(run['result']) if run['result'] and run['status'] != 'success' else None
                        run['request'] = json.loads(run['request']) if run['request'] else None
                        run['attachments'] = inputs.get(identity, {}).get('attachments', []) if run['status'] != 'success' else []
                        runs.append(run)
            next_cursor = None
            if has_more:
                oldest = rows[-1]
                next_cursor = base64.urlsafe_b64encode(json.dumps(
                    [session_id, oldest['stamp'], oldest['kind'], oldest['id']], separators=(',', ':')).encode()).decode()
        return {'turns': turns, 'runs': runs, 'trace': events, 'history_page': {'next_cursor': next_cursor}}

    def search_sessions(self, search: str = "", offset: int = 0, limit: int | None = 30) -> dict:
        where = "WHERE (?='' OR instr(lower(session_title || ' ' || preview),lower(?))>0)"
        with self.connect() as db:
            total = db.execute("SELECT count(*) FROM session_summaries " + where, (search, search)).fetchone()[0]
            rows = db.execute("SELECT * FROM session_summaries " + where + " ORDER BY pinned DESC,updated_at DESC,session_id LIMIT ? OFFSET ?",
                              (search, search, limit if limit is not None else -1, offset)).fetchall()
        return {"items": [{**dict(row), "pinned": bool(row["pinned"])} for row in rows], "total": total}

    def session_summary(self, session_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM session_summaries WHERE session_id=?", (session_id,)).fetchone()
        return {**dict(row), "pinned": bool(row["pinned"])} if row else None

    def update_session(self, session_id: str, title: str | None, pinned: bool | None) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM session_summaries WHERE session_id=?", (session_id,)).fetchone():
                raise LookupError("会话不存在")
            if title is not None:
                title = title.strip()
                if not title or len(title) > 80:
                    raise ValueError("会话名称须为 1–80 个字符")
                db.execute("UPDATE session_summaries SET session_title=? WHERE session_id=?", (title, session_id))
            if pinned is not None:
                db.execute("UPDATE session_summaries SET pinned=? WHERE session_id=?", (int(pinned), session_id))
        return self.session_summary(session_id)

    def delete_session(self, session_id: str) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM runs WHERE session_id=? AND status='running'", (session_id,)).fetchone():
                raise ValueError("该会话正在执行，请先停止生成再删除")
            db.execute("DELETE FROM events WHERE run_id IN (SELECT id FROM runs WHERE session_id=?)", (session_id,))
            for table, column in (("turns", "session_id"), ("messages", "session_id"), ("runs", "session_id"), ("sessions", "id"), ("session_summaries", "session_id")):
                db.execute(f"DELETE FROM {table} WHERE {column}=?", (session_id,))

    def append_turn(self, session_id: str, turn: dict[str, Any], limit: int = 20) -> None:
        # Only model context is truncated, never the persistent history.
        with self.connect() as db:
            inserted = db.execute("INSERT OR IGNORE INTO turns VALUES(?,?,?,?)", (
                turn.get("run_id") or str(uuid.uuid4()), session_id,
                turn.get("timestamp") or time.time(), json.dumps(turn, ensure_ascii=False)))
            if inserted.rowcount:
                self._touch_summary(db, session_id, turn.get("query", ""), turn.get("timestamp") or time.time(), 1)

    def start_run(self, run_id: str, session_id: str, query: str, request: dict | None = None) -> None:
        # Store identifiers only, never arbitrary context or a provider configuration.
        safe_request = {key: value for key, value in (request or {}).items()
                        if key in {"knowledge_base_id", "search_scope", "thinking_mode", "model_profile"}
                        and isinstance(value, str)}
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO sessions VALUES(?,?)", (session_id, time.time()))
            db.execute("INSERT INTO runs(id,session_id,status,started_at,query,request) VALUES(?,?,'running',?,?,?)",
                       (run_id, session_id, time.time(), query,
                        json.dumps(safe_request, ensure_ascii=False) if request is not None else None))
            self._touch_summary(db, session_id, query, time.time())

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
            db.execute("INSERT OR IGNORE INTO events SELECT ?,?,? WHERE EXISTS(SELECT 1 FROM runs WHERE id=?)", (
                event["run_id"], event["seq"], json.dumps(event, ensure_ascii=False), event["run_id"]))

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
                 "request": json.loads(row["request"]) if row["request"] else None,
                 "result": json.loads(row["result"]) if row["result"] else None} for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return {**dict(row), "request": json.loads(row["request"]) if row["request"] else None,
                "result": json.loads(row["result"]) if row["result"] else None} if row else None

    def search_runs(self, search: str, status: str, offset: int, limit: int) -> dict:
        where = "WHERE (?='' OR instr(lower(query),lower(?))>0) AND (?='' OR status=?)"
        params = (search, search, status, status)
        with self.connect() as db:
            total = db.execute("SELECT count(*) FROM runs " + where, params).fetchone()[0]
            rows = db.execute("SELECT id,session_id,status,started_at,finished_at,query,error FROM runs "
                              + where + " ORDER BY started_at DESC LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
        return {"items": [dict(row) for row in rows], "total": total}
