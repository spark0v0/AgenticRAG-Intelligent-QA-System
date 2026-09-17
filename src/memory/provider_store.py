"""Local provider settings. Windows credentials are protected by the current user's DPAPI."""
from __future__ import annotations

import base64
import ctypes
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from utils.execution import register_secret


def protect(value: str, decrypt: bool = False) -> str:
    if not value:
        return ""
    if os.name != "nt":
        if decrypt and value.startswith("dpapi:"):
            raise ValueError("此凭据由 Windows 用户加密，请在当前系统重新设置")
        return value.removeprefix("local:") if decrypt else "local:" + value
    if decrypt and not value.startswith("dpapi:"):
        return value.removeprefix("local:")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    raw = base64.b64decode(value[6:]) if decrypt else value.encode("utf-8")
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError("无法读取本机加密凭据，请重新设置")
    try:
        result = ctypes.string_at(target.data, target.size)
        return result.decode("utf-8") if decrypt else "dpapi:" + base64.b64encode(result).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


class ProviderStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            path.parent.chmod(0o700)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS providers (
                    id TEXT PRIMARY KEY, settings TEXT NOT NULL, secret TEXT NOT NULL,
                    checked_at REAL, check_ok INTEGER, check_message TEXT
                );
                CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
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

    def list(self, private=False):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM providers ORDER BY rowid").fetchall()
        items = []
        for row in rows:
            item = {**json.loads(row["settings"]), "id": row["id"], "has_key": bool(row["secret"]),
                    "checked_at": row["checked_at"], "check_ok": bool(row["check_ok"]) if row["check_ok"] is not None else None,
                    "check_message": row["check_message"]}
            if private:
                item["api_key"] = protect(row["secret"], decrypt=True)
                register_secret(item["api_key"])
            items.append(item)
        return items

    def save(self, settings: dict, identity: str | None = None):
        key = settings.pop("api_key", "")
        clear = settings.pop("clear_key", False)
        identity = identity or str(uuid.uuid4())
        with self.connect() as db:
            previous = db.execute("SELECT secret FROM providers WHERE id=?", (identity,)).fetchone()
            secret = protect(key) if key else (previous[0] if previous and not clear else "")
            db.execute("""INSERT INTO providers VALUES(?,?,?,NULL,NULL,NULL)
                ON CONFLICT(id) DO UPDATE SET settings=excluded.settings,secret=excluded.secret,
                checked_at=NULL,check_ok=NULL,check_message=NULL""", (identity, json.dumps(settings), secret))
        register_secret(key)
        return identity

    def remove(self, identity: str):
        with self.connect() as db:
            db.execute("DELETE FROM providers WHERE id=?", (identity,))

    def record_check(self, identity: str, ok: bool, message: str, expected: dict):
        with self.connect() as db:
            row = db.execute("SELECT settings,secret FROM providers WHERE id=?", (identity,)).fetchone()
            if row is None:
                return False
            current = json.loads(row["settings"])
            if (any(current[key] != expected[key] for key in ("base_url", "protocol"))
                    or protect(row["secret"], decrypt=True) != expected["api_key"]):
                return False
            db.execute("UPDATE providers SET checked_at=?,check_ok=?,check_message=? WHERE id=?",
                       (time.time(), int(ok), message, identity))
        return True

    def default(self, value: str | None = None):
        with self.connect() as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO preferences VALUES('default',?)", (value,))
            row = db.execute("SELECT value FROM preferences WHERE key='default'").fetchone()
        return row[0] if row else None

    def profiles(self):
        result = {}
        for provider in self.list(private=True):
            for model in provider["models"]:
                if not model["enabled"]:
                    continue
                identity = f"managed:{provider['id']}:{model['model_name']}"
                endpoint = provider["base_url"].rstrip("/")
                suffix = {"ollama": "/api/generate", "xinference": "/chat/completions"}.get(provider["protocol"], "")
                result[identity] = {"id": identity, "label": model["label"], "config": {
                    **model, "provider": provider["protocol"], "base_url": endpoint + suffix,
                    "api_key": provider["api_key"], "managed_credentials": True,
                    "timeout_seconds": provider["timeout_seconds"],
                }}
        return result
