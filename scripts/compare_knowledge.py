"""Small reproducible retrieval probe, not an accuracy benchmark. Uses downloaded real embeddings."""
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
os.environ.setdefault('AGENTICRAG_EMBEDDING_CACHE', str(ROOT / 'data/knowledge/models'))
from knowledge.service import KnowledgeService

directory = ROOT / '.cache' / ('retrieval-probe-' + uuid.uuid4().hex)
service = KnowledgeService(directory, start_worker=False)
kb = service.create('固定小样本检索比较', 'hybrid')['id']
documents = {
    '差旅制度.md': '# 差旅报销\n出差人员应在返回后五个工作日内提交发票与行程单，经部门负责人审批后由财务付款。',
    '账号安全.md': '# 找回账号\n忘记登录密码时，在登录页面选择重置密码，通过注册邮箱收到的验证码完成身份验证后设置新密码。',
    '项目交付.md': '# 发布要求\n交付前必须完成类型检查、生产构建和核心冒烟验证。上线后监控服务日志，出现故障时回退上一版本。',
}
for name, body in documents.items():
    service.upload(kb, name, body.encode())
    service.process_next()
failed = [doc for doc in service.documents(kb) if doc['status'] != 'completed']
if failed:
    raise SystemExit('真实模型索引未完成：' + str(failed[0]['error']))
queries = [('差旅报销需要什么材料？', '差旅制度.md'), ('忘了口令怎么恢复登录？', '账号安全.md'), ('交付之前要验证哪些内容？', '项目交付.md')]
report = {'fixture_only': True, 'model': 'BAAI/bge-small-zh-v1.5', 'dimensions': 512,
          'documents': documents, 'comparisons': [], 'note': '3 个固定小样本，仅观察命中排序与耗时，不能推导真实召回率或提升比例。'}
for query, expected in queries:
    for mode in ['keyword', 'semantic', 'hybrid']:
        started = time.perf_counter()
        result = service.search(kb, query, 3, mode)
        report['comparisons'].append({'query': query, 'expected': expected, 'mode': mode,
            'sources': [item['source'] for item in result['documents']], 'elapsed_ms': round((time.perf_counter() - started) * 1000, 1)})
destination = ROOT / 'docs/knowledge-retrieval-probe.json'
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report['comparisons'], ensure_ascii=False, indent=2))
service.close()
