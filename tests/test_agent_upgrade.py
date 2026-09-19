"""Offline regressions for retrieval policy and evidence contracts, no paid calls."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from agents.base_agent import AgentInput
from agents.router import Router
from agents.planner import Planner
from agents.critic import Critic
from agents.generator import Generator
from core.rag_system import AgenticRAGSystem
from retrieval.hybrid_store import HybridKnowledgeBase, retrieval_query
from tests.workbench_fixtures import fixture_config
from tools.web_search import search_web


def test_clear_routing_and_scope_do_not_call_model(monkeypatch):
    router = Router({'use_llm': True})
    async def forbidden(*args):
        raise AssertionError('Unnecessary classification call')
    monkeypatch.setattr(router, '_classify_with_llm', forbidden)
    async def run():
        for query, context, expected in [
            ('你好', {}, 'direct'), ('https://example.com 的代码接口', {}, 'retrieval'),
            ('2+3', {}, 'retrieval'), ('智能体', {'search_scope': 'local'}, 'retrieval'),
            ('最新资料', {'search_scope': 'web'}, 'retrieval'),
        ]:
            result = await router.process(AgentInput(query=query, context=context))
            assert result.metadata['route'] == expected
            assert result.metadata['classification_model_called'] is False
            if 'https' in query:
                assert result.metadata['intent'] != 'math'
    asyncio.run(run())


def test_chinese_bm25_fusion_and_query_focused_excerpt(tmp_path, monkeypatch):
    documents = tmp_path / 'documents'
    documents.mkdir()
    (documents / 'memory.txt').write_text('会话记忆使用数据库保存历史消息，支持多轮对话恢复。', encoding='utf8')
    (documents / 'other.txt').write_text('天气预报提供温度和降水概率。', encoding='utf8')
    # Explicit fixture injection: production intentionally excludes .cache and tests.
    monkeypatch.setattr(HybridKnowledgeBase, '_iter_candidate_paths', lambda self, root: root.glob('*.txt'))
    kb = HybridKnowledgeBase([str(documents)], ['*.txt'], persist_dir=str(tmp_path / 'index'))
    found = kb.search('如何保存会话历史消息')
    assert found and found[0]['source'].endswith('memory.txt')
    assert found[0]['metadata']['fusion'] == 'rrf_bm25_hash'
    assert kb.search('unrelated_unique_identifier') == []
    assert retrieval_query('根据本地文档，用一句话说明会话如何持久化，并引用来源。') == '会话如何持久化'
    generator = Generator({'max_context_chars': 500}, {})
    compressed = generator._compress_documents([{'source': 'a', 'score': 1,
        'content': '无关开头。' * 150 + '会话历史消息保存在 SQLite 数据库。'}], '会话历史消息')
    assert 'SQLite' in compressed[0]['content']
    assert sum(len(d['content']) for d in compressed) <= 500


def test_critic_accepts_concise_grounded_answer_and_rejects_unknown_ids():
    async def run():
        critic = Critic({})
        context = {'mode': 'grounded', 'content': '使用 SQLite。[S1]', 'source_map': [{'citation_id': 'S1'}]}
        valid = await critic.process(AgentInput(query='如何保存历史', context=context))
        assert not valid.metadata['need_revision']
        bad = await critic.process(AgentInput(query='如何保存历史', context={**context, 'content': '答案[S9]'}))
        assert bad.metadata['need_revision'] and bad.metadata['unknown_citations'] == ['S9']
        abstain = await critic.process(AgentInput(query='未知问题', context={'mode': 'grounded', 'content': '证据不足，无法确认。'}))
        assert not abstain.metadata['need_revision']
    asyncio.run(run())


def test_structured_planner_outputs_executable_queries(monkeypatch):
    class Client:
        is_available = True
        async def generate(self, *args):
            return SimpleNamespace(error=None, content=json.dumps({'rewritten_query': '比较两种检索', 'search_queries': ['BM25 检索', '向量检索']}))
    monkeypatch.setattr('agents.planner.build_model_client', lambda cfg: Client())
    result = asyncio.run(Planner({}).process(AgentInput(query='比较两种检索', context={'complexity': 0.8, 'model_config': {'model_name': 'fixture'}})))
    assert result.metadata['planning_source'] == 'structured_model'
    assert result.metadata['search_queries'] == ['BM25 检索', '向量检索']
    assert result.metadata['strategy'] == 'parallel'
    simple = asyncio.run(Planner({}).process(AgentInput(query='什么是检索', context={'model_config': {'model_name': 'fixture'}})))
    assert simple.metadata['planning_source'] == 'bounded_template'


def test_rag_final_evidence_and_single_generation_persist(tmp_path, monkeypatch):
    config = fixture_config(tmp_path)
    config['system']['max_retries'] = 1
    system = AgenticRAGSystem(config)
    generation_calls = []
    class Client:
        provider = 'openai'
        model_name = 'fixture'
        supports_vision = False
        async def generate(self, system_prompt, user_prompt, **kwargs):
            generation_calls.append(user_prompt)
            assert '检索证据' in user_prompt and '[S1]' in user_prompt
            return SimpleNamespace(provider='openai', model_name='fixture', usage={}, error=None, content='工作台支持多轮问答。[S1]')
    monkeypatch.setattr(system.generator, '_get_model_client', lambda context: Client())
    result = asyncio.run(system.query('AgenticRAG 工作台', {'search_scope': 'local'}))
    assert len(generation_calls) == 1
    assert result['source_map'] and result['retrieval_plan']['search_scope'] == 'local'
    assert result['evaluation']['revision_count'] == 0
    restored = system.get_session_detail(result['session_id'])['messages'][-1]
    assert restored['content'] == result['answer']
    assert restored['result']['source_map'] == result['source_map']
    assert restored['result']['timing'] == result['timing']


def test_web_search_keeps_success_when_one_engine_fails(monkeypatch):
    monkeypatch.setenv('WEB_SEARCH_PROVIDER', 'public')
    async def handle(request):
        if request.url.host == 'api.duckduckgo.com':
            return httpx.Response(503)
        return httpx.Response(200, json={'query': {'search': [{'title': '检索', 'snippet': '真实接口结构的隔离夹具'}]}})
    result = asyncio.run(search_web('检索', 3, transport=httpx.MockTransport(handle)))
    assert result.status == 'success' and len(result.documents) == 1
    assert result.metadata['partial'] is True
    assert result.metadata['engine_errors'][0]['engine'] == 'duckduckgo'


def test_tavily_results_are_evidence_not_generated_answer(monkeypatch):
    monkeypatch.setenv('WEB_SEARCH_PROVIDER', 'tavily')
    monkeypatch.setenv('TAVILY_API_KEY', 'fixture-only')
    async def handle(request):
        assert request.headers['Authorization'] == 'Bearer fixture-only'
        body = json.loads(request.content)
        assert body['include_answer'] is False and body['search_depth'] == 'basic'
        return httpx.Response(200, json={'answer': 'must not be used', 'results': [
            {'url': 'https://example.org/a', 'title': 'Evidence', 'content': 'Retrieved text'},
            {'url': 'javascript:alert(1)', 'content': 'unsafe'},
            {'url': 'https://example.org/a', 'content': 'duplicate'}]})
    result = asyncio.run(search_web('question', 3, transport=httpx.MockTransport(handle)))
    assert result.status == 'success' and len(result.documents) == 1
    assert result.documents[0].content == 'Retrieved text'
    assert 'fixture-only' not in result.model_dump_json()


def test_tavily_failures_are_actionable_and_do_not_fallback(monkeypatch):
    monkeypatch.setenv('WEB_SEARCH_PROVIDER', 'tavily')
    monkeypatch.delenv('TAVILY_API_KEY', raising=False)
    assert asyncio.run(search_web('query', 3)).metadata['reason'] == 'not_configured'
    monkeypatch.setenv('TAVILY_API_KEY', 'fixture-only')
    for code, reason in [(401, 'unauthorized'), (429, 'quota'), (500, 'unavailable'), (200, 'no_results')]:
        calls = []
        async def handle(request):
            calls.append(request.url.host)
            return httpx.Response(code, json={'results': [], 'error': 'fixture-only'})
        result = asyncio.run(search_web('query', 3, transport=httpx.MockTransport(handle)))
        assert result.metadata['reason'] == reason
        assert calls == ['api.tavily.com']
        assert 'fixture-only' not in result.model_dump_json()
        notice = Generator._build_live_data_notice(None, 'query', [
            {'tool': 'web_search', **result.model_dump()}])
        assert result.error in notice


def test_critic_retry_uses_new_query_and_persists_new_sources(tmp_path, monkeypatch):
    config = fixture_config(tmp_path)
    config['system']['max_retries'] = 1
    system = AgenticRAGSystem(config)
    calls = []
    async def invoke(name, payload):
        calls.append(payload['query'])
        docs = [] if len(calls) == 1 else [{'content': '历史使用数据库保存', 'source': 'fixture.txt', 'score': 1}]
        return {'status': 'success', 'documents': docs}
    monkeypatch.setattr(system.retriever.registry, 'invoke', invoke)
    class Client:
        provider = 'openai'
        model_name = 'fixture'
        supports_vision = False
        async def generate(self, *args, **kwargs):
            answer = '使用数据库。' if len(calls) == 1 else '历史使用数据库保存。[S1]'
            return SimpleNamespace(provider='openai', model_name='fixture', usage={}, error=None, content=answer)
    monkeypatch.setattr(system.generator, '_get_model_client', lambda context: Client())
    result = asyncio.run(system.query('如何保存会话历史', {'thinking_mode': 'retrieval', 'tools': ['knowledge_base_search'], 'retrieval_rounds': 1}))
    assert len(calls) == 2 and calls[0] != calls[1]
    assert result['source_map'][0]['source'] == 'fixture.txt'
    assert result['evaluation']['revision_count'] == 1
    assert result['retrieval_plan']['critic_retry']
    assert system.get_session_detail(result['session_id'])['messages'][-1]['content'] == result['answer']
