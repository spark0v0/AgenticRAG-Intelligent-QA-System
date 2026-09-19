"""Explicit one-time download. No API key, model-provider call or reference-project writes."""
import os
from pathlib import Path
from fastembed import TextEmbedding

root = Path(__file__).resolve().parents[1]
cache = Path(os.getenv('AGENTICRAG_EMBEDDING_CACHE', str(root / 'data/knowledge/models')))
print('下载中文 BGE small ONNX 模型（约 90 MB），保存到当前项目模型缓存。')
model = TextEmbedding('BAAI/bge-small-zh-v1.5', cache_dir=str(cache), threads=2)
vector = next(model.query_embed('知识库检索'))
print(f'模型已就绪，实际输出维度：{len(vector)}')
