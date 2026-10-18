"""Local MCP configuration and discovered schemas; no credential values are stored."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator


class MCPSettings(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    transport: Literal["stdio", "streamable_http"] = "streamable_http"
    url: str = Field(default="", max_length=500)
    command: str = Field(default="", max_length=500)
    args: list[str] = Field(default_factory=list, max_length=40)
    env_names: list[str] = Field(default_factory=list, max_length=20)
    token_env: str = Field(default="", max_length=100)
    timeout_seconds: int = Field(default=15, ge=3, le=20)

    @field_validator("name", "command", "url", "token_env")
    @classmethod
    def clean_text(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError("字段不能包含控制字符")
        return value.strip()

    @model_validator(mode="after")
    def connection(self):
        import re
        if not self.name:
            raise ValueError("请填写服务名称")
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", value)
               for value in self.env_names + ([self.token_env] if self.token_env else [])):
            raise ValueError("凭据仅填写后端环境变量名")
        if any(not isinstance(arg, str) or len(arg) > 1000 or "\x00" in arg for arg in self.args):
            raise ValueError("启动参数无效")
        if self.transport == "streamable_http":
            url = urlsplit(self.url)
            if (url.scheme not in {"http", "https"} or not url.hostname or url.username
                    or url.password or url.query or url.fragment):
                raise ValueError("地址必须是无凭据、查询参数的 HTTP(S) 服务地址")
            if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("远程供应商必须使用 HTTPS，本机服务可使用 HTTP")
            self.command, self.args, self.env_names = "", [], []
        else:
            if not self.command:
                raise ValueError("请填写可执行程序路径")
            self.url, self.token_env = "", ""
        return self


class ToolSettingsStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS mcp_servers (
                id TEXT PRIMARY KEY, settings TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 0, selected TEXT NOT NULL DEFAULT '[]',
                tools TEXT NOT NULL DEFAULT '[]', checked_at REAL, check_ok INTEGER,
                check_message TEXT NOT NULL DEFAULT '', last_call TEXT)""")
        if os.name != "nt":
            path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM mcp_servers ORDER BY rowid").fetchall()
        return [{**json.loads(r["settings"]), "id": r["id"], "revision": r["revision"],
                 "enabled": bool(r["enabled"]), "selected_tools": json.loads(r["selected"]),
                 "tools": json.loads(r["tools"]), "checked_at": r["checked_at"],
                 "check_ok": None if r["check_ok"] is None else bool(r["check_ok"]),
                 "check_message": r["check_message"], "last_call": json.loads(r["last_call"]) if r["last_call"] else None}
                for r in rows]

    def get(self, identity):
        item = next((item for item in self.list() if item["id"] == identity), None)
        if item is None:
            raise LookupError("MCP 服务不存在或已删除")
        return item

    def save(self, settings: MCPSettings, identity=None):
        if identity:
            self.get(identity)
        else:
            if len(self.list()) >= 12:
                raise ValueError("最多可配置 12 个 MCP 服务")
            identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("""INSERT INTO mcp_servers(id,settings) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET
                settings=excluded.settings, revision=revision+1, enabled=0, selected='[]', tools='[]',
                checked_at=NULL, check_ok=NULL, check_message='', last_call=NULL""",
                (identity, settings.model_dump_json()))
        return identity

    def record_check(self, identity, revision, tools, ok, message):
        with self.connect() as db:
            # Discovery invalidates prior authorization: schemas may have changed.
            return db.execute("""UPDATE mcp_servers SET tools=?, checked_at=?, check_ok=?, check_message=?,
                enabled=0, selected='[]', last_call=NULL, revision=revision+1 WHERE id=? AND revision=?""",
                (json.dumps(tools, ensure_ascii=False), time.time(), ok, message, identity, revision)).rowcount == 1

    def activate(self, identity, enabled, names):
        with self.connect() as db:
            row = db.execute("SELECT * FROM mcp_servers WHERE id=?", (identity,)).fetchone()
            if not row:
                raise LookupError("MCP 服务不存在或已删除")
            permitted = {t["name"] for t in json.loads(row["tools"]) if t.get("read_only")}
            if enabled and (not row["check_ok"] or not names or not set(names) <= permitted):
                raise ValueError("请先连接并选择已声明只读的工具")
            others = db.execute("SELECT selected FROM mcp_servers WHERE enabled=1 AND id<>?", (identity,)).fetchall()
            if enabled and len(set(names)) + sum(len(json.loads(r[0])) for r in others) > 32:
                raise ValueError("最多同时启用 32 个外部工具，请先停用不需要的工具")
            db.execute("UPDATE mcp_servers SET enabled=?, selected=?, revision=revision+1 WHERE id=?",
                       (enabled, json.dumps(list(dict.fromkeys(names)) if enabled else []), identity))

    def record_call(self, identity, revision, result):
        with self.connect() as db:
            db.execute("UPDATE mcp_servers SET last_call=? WHERE id=? AND revision=?",
                       (json.dumps(result, ensure_ascii=False), identity, revision))

    def remove(self, identity):
        with self.connect() as db:
            db.execute("DELETE FROM mcp_servers WHERE id=?", (identity,))
