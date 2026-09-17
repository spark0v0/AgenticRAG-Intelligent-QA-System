"""Focused checks for credential boundaries, configuration persistence and run navigation."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient
from api.main import app
from api import providers
from memory.provider_store import ProviderStore
from memory.sqlite_memory import SessionMemory
from utils.execution import public_data


def settings():
    return {"name": "Isolated test", "protocol": "openai", "base_url": "https://example.invalid/v1",
            "api_key": "fixture-secret-not-real", "timeout_seconds": 30,
            "models": [{"model_name": "fixture", "label": "Fixture", "enabled": True,
                        "supports_streaming": True, "supports_vision": False, "max_tokens": 100}]}


def test_secret_roundtrip_retention_clear_and_redaction(tmp_path):
    path = tmp_path / "settings" / "providers.sqlite3"
    store = ProviderStore(path)
    identity = store.save(settings())
    assert "fixture-secret-not-real" not in json.dumps(store.list())
    if os.name == "nt":
        assert b"fixture-secret-not-real" not in path.read_bytes()
    store.save({**settings(), "api_key": ""}, identity)
    assert store.list(private=True)[0]["api_key"] == "fixture-secret-not-real"
    assert public_data("failure fixture-secret-not-real") == "failure [redacted]"
    assert identity in next(iter(store.profiles()))
    old = store.list(private=True)[0]
    store.save({**settings(), "api_key": "", "clear_key": True}, identity)
    assert not store.list()[0]["has_key"]
    assert not store.record_check(identity, True, "outdated connection", old)


def test_local_provider_api_does_not_echo_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "_store", ProviderStore(tmp_path / "settings" / "providers.sqlite3"))
    monkeypatch.setattr(providers, "refresh_systems", lambda: None)
    with TestClient(app) as client:
        assert client.post("/api/settings/providers", json=settings()).status_code == 403
        headers = {"X-Workbench-Request": "1"}
        assert client.post("/api/settings/providers", json=settings(), headers={**headers, "Origin": "https://untrusted.invalid"}).status_code == 403
        response = client.post("/api/settings/providers", json=settings(), headers=headers)
        assert response.status_code == 200
        assert "api_key" not in client.get("/api/settings/providers").text
        response = client.post("/api/settings/providers", json={**settings(), "api_key": "fixture-secret-not-real" * 500}, headers=headers)
        assert response.status_code == 422
        assert "fixture-secret-not-real" not in response.text
        assert client.post("/api/settings/providers", json={**settings(), "base_url": "https://user:secret@example.invalid"}, headers=headers).status_code == 422


def test_run_pagination_filter_and_detail(tmp_path):
    memory = SessionMemory(tmp_path / "history.sqlite3")
    memory.start_run("one", "session", "RAG evidence")
    memory.finish_run("one", "success", {"answer": "stored"})
    memory.start_run("two", "session", "Other question")
    memory.finish_run("two", "cancelled")
    assert memory.search_runs("evidence", "success", 0, 10)["total"] == 1
    assert memory.search_runs("", "", 1, 1)["items"][0]["id"] == "one"
    assert memory.get_run("one")["session_id"] == "session"
    assert memory.get_run("one")["result"]["answer"] == "stored"
