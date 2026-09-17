"""Small offline regressions for the workbench's highest-risk contracts."""
import asyncio
import json
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
    path = tmp_path / "sessions.json"
    original = json.dumps({"legacy": [{"query": "old", "response": "answer", "timestamp": 1}]})
    path.write_text(original, encoding="utf-8")
    SessionMemory(path)
    memory = SessionMemory(path)
    assert len(memory.get_session("legacy")) == 1
    assert path.read_text(encoding="utf-8") == original
    with memory.connect() as db:
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 2


def test_cancel_first_run_then_retry_and_persist_final_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("models.client.AsyncOpenAI", fixture_client)
    monkeypatch.setattr(ModelClient, "select_tools", select_fixture_tools)
    async def scenario():
        system = build_system(tmp_path)
        events = []
        first, task = system.start_query("你好", session_id="conversation", listener=events.append)
        await asyncio.sleep(0.02)
        with pytest.raises(ValueError):
            system.start_query("duplicate", session_id="conversation")
        assert system.cancel_run(first.run_id)
        await asyncio.gather(task, return_exceptions=True)
        assert system.memory.list_runs("conversation")[0]["status"] == "cancelled"
        assert not system._run_tasks
        result = await system.query("2+3", session_id="conversation")
        detail = system.get_session_detail("conversation")
        assert result["answer"] == detail["messages"][-1]["content"]
        assert detail["messages"][-1]["result"]["source_map"] == result["source_map"]
        assert len(system.memory.get_session("conversation")) == 1
        assert any(e["type"] == "completed" for e in detail["trace"])
        assert not system.cancel_run(first.run_id)
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
