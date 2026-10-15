"""Core contracts only. Every file/database/vector is under pytest's temporary directory."""
import asyncio
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from knowledge.service import KnowledgeService
from knowledge.parsing import extract, split
from agents.generator import Generator
from utils.execution import Execution, current_execution


def service(tmp_path):
    return KnowledgeService(tmp_path / 'knowledge', start_worker=False)


def test_upload_search_dedup_isolation_delete_and_snapshot(tmp_path):
    svc = service(tmp_path)
    first = svc.create('产品资料', 'keyword')['id']
    second = svc.create('其他资料', 'keyword')['id']
    body = '# 差旅制度\n\n差旅报销需要提供发票，并经过部门负责人审批。'.encode()
    doc = svc.upload(first, '差旅.md', body)['document']
    assert svc.search(first, '差旅报销')['metadata']['state'] == 'indexing'
    assert svc.upload(first, '不同名称.md', body)['duplicate']
    assert not svc.upload(second, '差旅.md', body)['duplicate']
    assert svc.process_next()
    found = svc.search(first, '差旅报销')
    assert found['metadata']['state'] == 'ready'
    assert all(item['metadata']['knowledge_base_id'] == first for item in found['documents'])
    assert svc.search(second, '差旅报销')['documents'] == []
    generator = Generator({}, {'provider': 'openai', 'model_name': 'fixture'})
    token = current_execution.set(Execution('session', 'run', False, lambda _: None))
    try:
        sources = generator._build_source_map(generator._compress_documents(found['documents'], '报销'))
        assert generator._build_source_map(list(reversed(found['documents'])))[0]['citation_id'] == sources[0]['citation_id']
    finally:
        current_execution.reset(token)
    source = sources[0]
    assert source['document_id'] == doc['id'] and source['version'] == doc['version']
    svc.delete_document(first, doc['id'])
    assert svc.search(first, '差旅报销')['documents'] == []
    assert svc.process_next()  # Deletes have priority over queued indexing.
    assert not (svc.root / 'files' / doc['id']).exists()
    assert not svc.evidence(first, doc['id'], source['chunk_id'])['original_available']
    assert '差旅' in source['excerpt']  # Historical snapshots are values, not live joins.
    svc.delete_library(first)
    assert all(k['id'] != first for k in svc.libraries())


def test_failure_retry_cancel_and_restart_recovery(tmp_path, monkeypatch):
    svc = service(tmp_path)
    kb = svc.create('恢复验证', 'keyword')['id']
    doc = svc.upload(kb, '说明.txt', '取消和重试不会重复创建文档。'.encode())['document']
    svc.cancel(kb, doc['id'])
    assert not svc.process_next()
    svc.retry(kb, doc['id'])
    svc.retry(kb, doc['id'])
    with svc.db() as db:
        assert db.execute("SELECT count(*) FROM jobs WHERE status='queued'").fetchone()[0] == 1
        db.execute("UPDATE jobs SET status='parsing' WHERE status='queued'")
        db.execute("UPDATE documents SET status='parsing' WHERE id=?", (doc['id'],))
    restarted = KnowledgeService(svc.root, start_worker=False)
    assert restarted.document(kb, doc['id'])['status'] == 'failed'
    restarted.retry(kb, doc['id'])
    assert restarted.process_next()
    assert restarted.document(kb, doc['id'])['status'] == 'completed'
    before = restarted.search(kb, '重复创建')['documents']
    def broken(*_):
        raise ValueError('夹具模拟解析失败')
    monkeypatch.setattr('knowledge.service.extract', broken)
    restarted.retry(kb, doc['id'])
    restarted.process_next()
    assert restarted.document(kb, doc['id'])['job']['status'] == 'failed'
    assert restarted.search(kb, '重复创建')['documents'] == before  # Failed rebuild keeps committed index.


def test_vector_delete_race_and_no_silent_fallback(tmp_path, monkeypatch):
    svc = service(tmp_path)
    kb = svc.create('向量边界', 'hybrid')['id']
    doc = svc.upload(kb, '向量.txt', '这是索引删除竞争条件的固定夹具。'.encode())['document']
    def unavailable(*args, **kwargs):
        raise ValueError('夹具模拟模型缺失')
    monkeypatch.setattr(svc.embed, 'encode', unavailable)
    svc.process_next()
    assert svc.document(kb, doc['id'])['status'] == 'failed'
    assert not svc.search(kb, '索引')['documents']
    def delete_during_embedding(texts, **kwargs):
        svc.delete_document(kb, doc['id'])
        return [[1.0] + [0.0] * 511 for _ in texts]  # Only a vector-shape fixture, not semantic validation.
    monkeypatch.setattr(svc.embed, 'encode', delete_during_embedding)
    svc.retry(kb, doc['id'])
    svc.process_next()
    svc.process_next()
    assert svc.document(kb, doc['id'], True)['status'] == 'deleted'
    assert svc._collection().count() == 0


def test_api_validation_pdf_position_and_upload(tmp_path, monkeypatch):
    svc = service(tmp_path)
    monkeypatch.setattr('knowledge.service._service', svc)
    from api.main import app
    headers = {'X-Workbench-Request': '1'}
    with TestClient(app) as client:
        kb = client.post('/api/knowledge', json={'name': '接口夹具', 'mode': 'keyword'}, headers=headers).json()['id']
        path = f'/api/knowledge/{kb}/documents'
        assert client.post(path, files={'files': ('../bad.txt', b'hello')}, headers=headers).status_code == 422
        assert client.post(path, files={'files': ('bad.txt', b'\x00binary')}, headers=headers).status_code == 422
        assert client.post(path, files={'files': ('bad.pdf', b'not pdf')}, headers=headers).status_code == 422
        assert client.post(path, content=b'', headers={**headers, 'Content-Length': str(33 * 1024 ** 2)}).status_code == 413
        result = client.post(path, files={'files': ('hello.md', '# Hello\n\nDocument evidence.'.encode())}, headers=headers)
        assert result.status_code == 202
        assert client.post(path, files={'files': ('hello.md', '# Hello\n\nDocument evidence.'.encode())}, headers=headers).json()['items'][0]['duplicate']
        svc.process_next()
        assert client.get(path).json()['items'][0]['status'] == 'completed'
        comparison = client.post(f'/api/knowledge/{kb}/compare', json={'query': 'evidence'}, headers=headers)
        assert comparison.status_code == 200
        modes = comparison.json()['results']
        assert [item['metadata']['state'] for item in modes] == ['ready', 'unavailable', 'unavailable']
        assert modes[0]['documents'][0]['ranking']['bm25_score'] > 0
        assert comparison.json()['timings']['semantic_ms'] is None
        assert client.post(f'/api/knowledge/{kb}/compare', json={'query': '   '}, headers=headers).status_code == 422
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 30 250 Td (Travel reimbursement requires receipts.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    chunks = split(extract(output.getvalue(), '.pdf'))
    assert chunks[0]['page'] == 1 and 'receipts' in chunks[0]['text']


def test_query_pipeline_keeps_selected_library_and_persists_evidence(tmp_path, monkeypatch):
    from tests.workbench_fixtures import fixture_client, fixture_config
    from core.rag_system import AgenticRAGSystem
    svc = service(tmp_path)
    monkeypatch.setattr('knowledge.service._service', svc)
    monkeypatch.setattr('models.client.AsyncOpenAI', fixture_client)
    kb = svc.create('测试专用资料', 'keyword')['id']
    doc = svc.upload(kb, '流程.md', '# 执行流程\nRouter 路由，Retriever 检索，Generator 生成回答。'.encode())['document']
    svc.process_next()
    config = fixture_config(tmp_path)
    config['retrieval']['knowledge_paths'] = []
    config['planner'] = {'use_llm': False}
    system = AgenticRAGSystem(config)
    async def run():
        result = await system.query('执行流程如何工作？', context={'search_scope': 'local', 'knowledge_base_id': kb, 'thinking_mode': 'retrieval'}, session_id='library-test')
        assert result['retrieval_plan']['selected_tools'] == ['library_search']
        assert result['source_map'][0]['document_id'] == doc['id']
        saved = system.get_session_detail('library-test')['messages'][-1]['result']
        assert saved['source_map'] == result['source_map']
        assert saved['answer'] == result['answer']
    asyncio.run(run())


def test_comparison_shares_embedding_and_keeps_modes_isolated(tmp_path, monkeypatch):
    svc = service(tmp_path)
    kb = svc.create('对比夹具', 'hybrid')['id']
    other = svc.create('禁止混入', 'hybrid')['id']
    calls = []
    def embedding(texts, query=False):
        calls.append(query)
        # Deliberately different lexical/semantic orders. This validates routing/ranking, not model quality.
        return [([1., 0.] if query or '收据' in text else [.6, .8]) + [0.] * 510 for text in texts]
    monkeypatch.setattr(svc.embed, 'encode', embedding)
    first = svc.upload(kb, '审批.txt', '报销须填写审批表格。'.encode())['document']
    second = svc.upload(kb, '费用.txt', '出差费用需要收据。'.encode())['document']
    svc.upload(other, '隔离.txt', '报销收据属于其他知识库。'.encode())
    while svc.process_next():
        pass
    calls.clear()
    result = svc.compare(kb, '报销')
    assert calls == [True]  # Query embedding is shared by semantic and hybrid modes.
    keyword, semantic, hybrid = result['results']
    assert keyword['documents'][0]['metadata']['document_id'] == first['id']
    assert semantic['documents'][0]['metadata']['document_id'] == second['id']
    assert hybrid['documents'][0]['metadata']['document_id'] == first['id']
    assert result['candidate_count'] == 2
    for mode_result in result['results']:
        mode = mode_result['metadata']['mode']
        assert all(doc['metadata']['knowledge_base_id'] == kb for doc in mode_result['documents'])
        normal = svc.search(kb, '报销', mode=mode)
        assert [{k: v for k, v in doc.items() if k != 'ranking'} for doc in mode_result['documents']] == normal['documents']
    rank = hybrid['documents'][0]['ranking']
    assert rank['keyword_rank'] == 1 and rank['semantic_rank'] == 2
    assert rank['rrf_score'] == pytest.approx(1 / 61 + 1 / 62)
    assert all(value >= 0 for value in result['timings'].values())
    svc.delete_document(kb, second['id'])
    assert all(doc['metadata']['document_id'] != second['id'] for mode in svc.compare(kb, '报销')['results'] for doc in mode['documents'])
    def unavailable(*args, **kwargs):
        raise RuntimeError('private-path-and-key-must-not-leak')
    monkeypatch.setattr(svc.embed, 'encode', unavailable)
    failed = svc.compare(kb, '报销')
    assert [mode['metadata']['state'] for mode in failed['results']] == ['ready', 'error', 'error']
    assert 'private-path' not in str(failed)
    assert failed['timings']['fusion_ms'] is None


def test_comparison_distinguishes_empty_pending_and_deleted(tmp_path, monkeypatch):
    svc = service(tmp_path)
    kb = svc.create('索引状态', 'keyword')['id']
    def forbidden(*args, **kwargs):
        pytest.fail('Keyword-only comparison must not load an embedding model')
    monkeypatch.setattr(svc.embed, 'encode', forbidden)
    assert svc.compare(kb, '流程')['results'][0]['metadata']['state'] == 'empty'
    doc = svc.upload(kb, '流程.txt', '请按审批流程提交申请。'.encode())['document']
    assert svc.compare(kb, '流程')['results'][0]['metadata']['state'] == 'indexing'
    svc.cancel(kb, doc['id'])
    assert svc.compare(kb, '流程')['results'][0]['metadata']['state'] == 'not_ready'
    svc.retry(kb, doc['id'])
    svc.process_next()
    assert svc.compare(kb, 'nonexistent')['results'][0]['metadata']['state'] == 'no_match'
    svc.delete_library(kb)
    with pytest.raises(LookupError):
        svc.compare(kb, '流程')
