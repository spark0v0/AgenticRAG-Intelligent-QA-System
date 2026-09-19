"""CPU Chinese semantic embeddings. No network or hash fallback during requests."""
from __future__ import annotations
import os
import threading
from pathlib import Path

MODEL = 'BAAI/bge-small-zh-v1.5'
DIMENSION = 512
# A separate collection per fingerprint prevents mixing incompatible vector spaces.
FINGERPRINT = 'bge-small-zh-v1_5-fastembed-512-paragraph-v1'


class Embedding:
    def __init__(self, root: Path):
        self.cache = Path(os.getenv('AGENTICRAG_EMBEDDING_CACHE', str(root / 'models')))
        self._model = None
        self._lock = threading.Lock()

    def encode(self, texts: list[str], query=False) -> list[list[float]]:
        with self._lock:
            if self._model is None:
                try:
                    from fastembed import TextEmbedding
                    self._model = TextEmbedding(MODEL, cache_dir=str(self.cache), threads=2,
                                                local_files_only=True)
                except Exception as exc:
                    raise ValueError('中文嵌入模型未就绪。请先运行 scripts/prepare_embedding.py；也可明确选择关键词模式') from exc
            try:
                iterator = self._model.query_embed(texts) if query else self._model.passage_embed(texts)
                vectors = [value.tolist() for value in iterator]
                if any(len(value) != DIMENSION for value in vectors):
                    raise ValueError('嵌入维度不匹配，需要重建索引')
                return vectors
            except Exception as exc:
                raise ValueError('中文嵌入执行失败，请检查模型缓存和可用内存；未降级为哈希向量') from exc
