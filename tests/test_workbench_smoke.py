"""Small offline regressions for the workbench's highest-risk contracts."""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.rag_system import AgenticRAGSystem
from memory.sqlite_memory import SessionMemory
from models.client import ModelClient
from utils.execution import Execution, current_execution
from tests.workbench_fixtures import fixture_config, fixture_client, select_fixture_tools


def build_system(tmp_path):
    return AgenticRAGSystem(fixture_config(tmp_path))


def test_legacy_migration_is_repeatable_and_non_destructive(tmp_path):
    from memory import SessionMemory as PublicMemory
    from memory.session_memory import SessionMemory as CompatibleMemory
    assert PublicMemory is CompatibleMemory is SessionMemory
    path = tmp_path / "sessions.json"
    original = json.dumps({"legacy": [{"query": "old", "response": "answer", "timestamp": 1}]})
    path.write_text(original, encoding="utf-8")
    SessionMemory(path)
    memory = SessionMemory(path)
    assert len(memory.get_session("legacy")) == 1
    assert path.read_text(encoding="utf-8") == original
    with memory.connect() as db:
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 2


def test_stream_completion_avoids_full_history_reads_and_keeps_json_compatibility(tmp_path, monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr('models.client.AsyncOpenAI', fixture_client)
    async def scenario():
        system = build_system(tmp_path)
        for index in range(25):
            system.memory.append_turn('long', {'query': f'old-{index}', 'response': 'fixture ' * 1000,
                                              'timestamp': index + 1})
        get_session = Mock(wraps=system.memory.get_session)
        get_events = Mock(wraps=system.memory.get_events)
        monkeypatch.setattr(system.memory, 'get_session', get_session)
        monkeypatch.setattr(system.memory, 'get_events', get_events)
        events = []
        execution, task = system.start_query('你好', session_id='long', listener=events.append)
        result = await task
        assert get_session.call_count == 0, 'Streaming completion must not reload all prior turns'
        assert get_events.call_count == 0, 'Already delivered events must not be reloaded for SSE completion'
        assert result['turn_count'] == 26
        assert not {'messages', 'execution_trace', 'capabilities'} & result.keys()
        assert events[-1]['type'] == 'completed'
        assert events[-1]['data']['result']['answer'] == result['answer']
        detail = system.get_session_detail('long')
        assert len(detail['messages']) == 52 and detail['trace']
        assert detail['runs'][-1]['id'] == execution.run_id
        assert detail['messages'][-1]['content'] == result['answer']
        # Existing non-streaming callers still receive the complete conversation and run trace.
        legacy = await system.query('你好', session_id='long')
        assert legacy['turn_count'] == 27 and len(legacy['messages']) == 54
        assert legacy['execution_trace'] and legacy['capabilities']
        assert legacy['messages'][-1]['content'] == legacy['answer']
    asyncio.run(scenario())


def test_cancel_first_run_then_retry_and_persist_final_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("models.client.AsyncOpenAI", fixture_client)
    monkeypatch.setattr(ModelClient, "select_tools", select_fixture_tools)
    async def scenario():
        system = build_system(tmp_path)
        events = []
        original_query = system._query
        async def wait_for_cancel(*args, **kwargs):
            await asyncio.Event().wait()
        monkeypatch.setattr(system, "_query", wait_for_cancel)
        request = {"knowledge_base_id": "library-a", "search_scope": "local", "thinking_mode": "retrieval",
                   "model_profile": "default"}
        first, task = system.start_query("你好", context=request, session_id="conversation", listener=events.append)
        await asyncio.sleep(0.02)
        with pytest.raises(ValueError):
            system.start_query("duplicate", session_id="conversation")
        assert system.cancel_run(first.run_id)
        await asyncio.gather(task, return_exceptions=True)
        assert system.memory.list_runs("conversation")[0]["status"] == "cancelled"
        assert SessionMemory(system.memory.storage_path).get_run(first.run_id)["request"] == request
        assert not system._run_tasks
        monkeypatch.setattr(system, "_query", original_query)
        result = await system.query("2+3", session_id="conversation")
        detail = system.get_session_detail("conversation")
        assert result["answer"] == detail["messages"][-1]["content"]
        assert detail["messages"][-1]["result"]["source_map"] == result["source_map"]
        assert len(system.memory.get_session("conversation")) == 1
        assert any(e["type"] == "completed" for e in detail["trace"])
        assert not system.cancel_run(first.run_id)
    asyncio.run(scenario())


def test_request_snapshot_upgrade_preserves_old_rows_and_allowlists_fields(tmp_path):
    path = tmp_path / "history.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE runs(id TEXT PRIMARY KEY, session_id TEXT, status TEXT, started_at REAL, finished_at REAL, query TEXT, result TEXT, error TEXT)")
        db.execute("INSERT INTO runs VALUES('old','s','cancelled',1,2,'original question',NULL,NULL)")
    memory = SessionMemory(path)
    memory.start_run("new", "s", "new question", {
        "knowledge_base_id": "kb", "search_scope": "local", "thinking_mode": "deep", "model_profile": "fixture",
        "api_key": "must-not-persist", "model_config": {"api_key": "must-not-persist"}, "images": ["private"],
    })
    memory.recover_interrupted_runs()
    reloaded = SessionMemory(path)
    runs = reloaded.list_runs("s")
    assert runs[0]["query"] == "original question" and runs[0]["request"] is None
    assert runs[1]["status"] == "error" and runs[1]["request"]["knowledge_base_id"] == "kb"
    assert set(runs[1]["request"]) == {"knowledge_base_id", "search_scope", "thinking_mode", "model_profile"}
    assert "must-not-persist" not in json.dumps(runs)


def test_failed_first_run_retains_request_without_a_successful_turn(tmp_path, monkeypatch):
    async def fail(*args, **kwargs):
        raise ValueError("fixture failure")
    async def scenario():
        system = build_system(tmp_path)
        monkeypatch.setattr(system, "_query", fail)
        request = {"knowledge_base_id": "library-b", "search_scope": "all", "thinking_mode": "deep", "model_profile": "default"}
        with pytest.raises(ValueError, match="fixture failure"):
            await system.query("question", request, session_id="failed")
        detail = system.get_session_detail("failed")
        assert detail["messages"] == []
        assert detail["runs"][0]["status"] == "error"
        assert detail["runs"][0]["request"] == request
    asyncio.run(scenario())


def test_openai_incremental_transport_and_close(monkeypatch):
    async def scenario(cancel=False):
        closed = False
        received = asyncio.Event()

        class Upstream(httpx.AsyncByteStream):
            async def __aiter__(self):
                for text in ["真实", "增量"]:
                    payload = {"id": "local", "object": "chat.completion.chunk", "created": 0, "model": "fixture",
                               "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
                    yield f"data: {json.dumps(payload)}\n\n".encode()
                    received.set()
                    if cancel:
                        await asyncio.Event().wait()
                yield b'data: {"id":"local","object":"chat.completion.chunk","created":0,"model":"fixture","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'

            async def aclose(self):
                nonlocal closed
                closed = True

        transport = httpx.MockTransport(lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Upstream()))
        monkeypatch.setattr("models.client.AsyncOpenAI", lambda **kw: AsyncOpenAI(**kw, http_client=httpx.AsyncClient(transport=transport)))
        events = []
        execution = Execution("session", "run", True, lambda _: None, events.append)
        execution.begin_answer()
        token = current_execution.set(execution)
        try:
            client = ModelClient({"provider": "openai", "api_key": "offline-fixture", "model_name": "fixture"})
            task = asyncio.create_task(client.generate_stream("system", "question"))
            if cancel:
                await received.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                result = await task
                assert result.content == "真实增量"
                assert len([e for e in events if e["type"] == "delta"]) == 2
            assert closed
        finally:
            current_execution.reset(token)
    asyncio.run(scenario())
    asyncio.run(scenario(cancel=True))


def test_removed_mock_provider_never_returns_a_success_answer():
    from agents.generator import Generator
    from agents.base_agent import AgentInput

    async def scenario():
        config = {"provider": "mock", "model_name": "retired"}
        response = await ModelClient(config).generate("system", "question")
        assert response.error and not response.content
        with pytest.raises(ValueError):
            await Generator({}, config).process(AgentInput(query="你好"))
    asyncio.run(scenario())
