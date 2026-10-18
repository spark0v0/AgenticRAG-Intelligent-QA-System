"""Core tool integration regressions, using temporary storage and local MCP only."""
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from api import tools as tool_api
from tools import managed
from tools.mcp_client import MCPConnection
from tools.registry import ToolRegistry
from tools.settings import MCPSettings, ToolSettingsStore
from models.client import ModelClient
from agents.retriever import Retriever

FIXTURE = str(Path(__file__).with_name('mcp_fixture.py').resolve())


def configuration():
    return MCPSettings(name='本地测试服务', transport='stdio', command=sys.executable, args=[FIXTURE])


def test_stdio_discovery_trial_schema_and_disable(tmp_path, monkeypatch):
    store = ToolSettingsStore(tmp_path / 'tools.sqlite3')
    monkeypatch.setattr(managed, '_store', store)
    identity = store.save(configuration())
    async def run():
        result = await managed.discover(identity)
        assert result['ok'], result
        record = store.get(identity)
        assert not record['enabled']
        assert len(record['tools']) == 3
        with pytest.raises(ValueError):
            store.activate(identity, True, ['unspecified_action'])
        store.activate(identity, True, ['city_info'])
        registry = ToolRegistry()
        specs = managed.configured_tools()
        registry.replace_external(specs)
        spec = specs[0]
        bad = await registry.invoke(spec.name, {'query': 'wrong schema'})
        assert bad['status'] == 'error'
        good = await registry.invoke(spec.name, {'city': '西安', 'days': 2})
        assert good['status'] == 'success', good
        assert '西安' in good['documents'][0]['content']
        assert store.get(identity)['last_call']['status'] == 'success'
        store.activate(identity, False, [])
        assert not managed.configured_tools()
        assert (await registry.invoke(spec.name, {'city': '西安'}))['status'] == 'error'
        # Stale discovery cannot overwrite later edits; restart preserves configuration.
        old = store.get(identity)
        store.save(configuration(), identity)
        assert not store.record_check(identity, old['revision'], [], True, 'stale')
        assert ToolSettingsStore(store.path).get(identity)['check_ok'] is None
        store.remove(identity)
        with pytest.raises(LookupError):
            store.get(identity)
    asyncio.run(run())


def test_http_transport_and_stdio_cancel(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, FIXTURE, str(port)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, env={**os.environ, 'PYTHONUTF8': '1'},
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.1):
                    break
            except OSError:
                time.sleep(.05)
        async def run():
            client = MCPConnection({'transport': 'streamable_http', 'url': f'http://127.0.0.1:{port}/mcp', 'timeout_seconds': 10})
            assert len(await client.list_tools()) == 3
            result = await client.call_tool('city_info', {'city': '上海'})
            assert not result['isError'] and '上海' in result['content'][0]['text']
            marker = tmp_path / 'cancel.txt'
            task = asyncio.create_task(MCPConnection(configuration().model_dump()).call_tool('slow_query', {'marker': str(marker)}))
            for _ in range(100):
                if marker.exists():
                    break
                await asyncio.sleep(.05)
            assert marker.exists()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert marker.read_text(encoding='utf8') == 'closed'
            timeout_marker = tmp_path / 'timeout.txt'
            with pytest.raises(TimeoutError):
                await MCPConnection({**configuration().model_dump(), 'timeout_seconds': 3}).call_tool('slow_query', {'marker': str(timeout_marker)})
            assert timeout_marker.read_text(encoding='utf8') == 'closed'
        asyncio.run(run())
    finally:
        process.terminate()
        process.wait(timeout=8)


def test_management_local_only_and_connection_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(managed, '_store', ToolSettingsStore(tmp_path / 'tools.sqlite3'))
    monkeypatch.setattr(tool_api, 'refresh_tools', lambda: None)
    app = FastAPI()
    app.include_router(tool_api.router, prefix='/api')
    with TestClient(app) as client:
        body = configuration().model_dump()
        assert client.post('/api/settings/mcp', json=body).status_code == 403
        headers = {'X-Workbench-Request': '1'}
        assert client.post('/api/settings/mcp', json=body, headers={**headers, 'Origin':'https://invalid.example'}).status_code == 403
        response = client.post('/api/settings/mcp', json={**body, 'command': 'missing-fixture-program'}, headers=headers)
        identity = response.json()['id']
        check = client.post(f'/api/settings/mcp/{identity}/discover', headers=headers).json()
        assert check['ok'] is False
        assert managed.get_store().get(identity)['check_ok'] is False
        assert client.patch(f'/api/settings/mcp/{identity}', json={'enabled':True, 'selected_tools':['city_info']}, headers=headers).status_code == 422
        assert client.delete(f'/api/settings/mcp/{identity}', headers=headers).status_code == 200
    with pytest.raises(ValueError):
        managed.validate_schema({'type':'object','properties':{'x':{'$ref':'https://example.invalid/schema'}}})


def test_model_arguments_and_explicit_scope(tmp_path, monkeypatch):
    from tests.workbench_fixtures import fixture_config
    from agents.base_agent import AgentInput
    config = fixture_config(tmp_path)
    retriever = Retriever(config.get('retrieval', {}), config)
    store = ToolSettingsStore(tmp_path / 'tools.sqlite3')
    monkeypatch.setattr(managed, '_store', store)
    identity = store.save(configuration())
    remote = {'name':'city_info', 'description':'City lookup', 'schema':{'type':'object','properties':{'city':{'type':'string'}},'required':['city']},'read_only':True}
    store.record_check(identity, 1, [remote], True, 'fixture schema')
    store.activate(identity, True, ['city_info'])
    spec = managed.make_spec(store.get(identity), remote)
    retriever.registry.register(spec)
    async def run():
        selected, _ = await retriever._select_tools('西安', 'fact', {'knowledge_base_id':'only-this', 'search_scope':'local'})
        assert selected == ['library_search']
        assert retriever._build_round_plan('question', 'fact', [spec.name], {}) == []
        plan = retriever._build_round_plan('question', 'fact', [spec.name], {'tool_arguments':{spec.name:{'city':'西安'}}})
        assert plan == [{'tool':spec.name,'payload':{'city':'西安'}}]
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def __init__(self, **kwargs): self.chat = SimpleNamespace(completions=self)
            async def create(self, **kwargs):
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(name=spec.name, arguments=json.dumps({'city':'西安'})))]))])
        monkeypatch.setattr('models.client.AsyncOpenAI', Client)
        model = ModelClient({'provider':'openai','model_name':'fixture','api_key':'fixture-key'})
        result = await model.select_tools('西安', [spec.as_function_schema()])
        assert result.arguments == {spec.name:{'city':'西安'}}
        assert result.used_function_calling
        output = await retriever.process(AgentInput(query='查询城市信息', context={'model_config':{'provider':'openai','model_name':'fixture','api_key':'fixture-key'}}))
        assert output.metadata['retrieval_plan']['selected_tools'] == [spec.name]
        assert output.metadata['tool_calls'][0]['status'] == 'success'
        assert '西安' in output.metadata['documents'][0]['content']
    asyncio.run(run())


def test_critic_does_not_repeat_external_query_on_empty_result(tmp_path, monkeypatch):
    from core.rag_system import AgenticRAGSystem
    from tests.workbench_fixtures import fixture_config
    from tools.base import ToolResult, ToolSpec

    config = fixture_config(tmp_path)
    config['system']['max_retries'] = 1
    system = AgenticRAGSystem(config)
    calls = []
    generations = []

    async def empty_result(payload):
        calls.append(payload.payload)
        return ToolResult(documents=[], metadata={'backend': 'mcp'})

    spec = ToolSpec(name='mcp_empty_fixture', description='Empty query fixture', handler=empty_result,
                    protocol='mcp', tags=['mcp', 'external'], metadata={'server_id': 'fixture'})
    system.retriever.registry.register(spec)

    async def select(*args):
        return [spec.name], {'arguments': {spec.name: {'city': '西安'}}}

    class Client:
        provider = 'openai'
        model_name = 'fixture'
        supports_vision = False
        async def generate(self, *args, **kwargs):
            generations.append(True)
            answer = '这里是查询回答。' if len(generations) == 1 else '证据不足，无法确认。'
            return SimpleNamespace(provider='openai', model_name='fixture', usage={}, error=None, content=answer)

    monkeypatch.setattr(system.retriever, '_select_tools', select)
    monkeypatch.setattr(system.generator, '_get_model_client', lambda context: Client())
    result = asyncio.run(system.query('查询西安城市信息', {'thinking_mode': 'retrieval', 'retrieval_rounds': 1}))
    assert len(generations) == 2 and len(calls) == 1
    assert result['source_map'] == []
    assert result['retrieval_plan']['critic_retry_skipped'] == 'external_tool_no_automatic_retry'
