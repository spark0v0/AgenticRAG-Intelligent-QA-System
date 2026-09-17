from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.execution import public_data

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,8}", re.UNICODE)
CODE_HINT_RE = re.compile(
    r"(from\s+\w+\s+import|def\s+\w+\(|class\s+\w+|async\s+def|return\s+|print\(|#include|public\s+class)",
    re.IGNORECASE,
)


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def is_code_like(text: str, source: str) -> bool:
    path = Path(source)
    if path.suffix.lower() in {".py", ".js", ".ts", ".java", ".cpp", ".go", ".rs"}:
        return True
    return bool(CODE_HINT_RE.search((text or "")[:240]))


class HashEmbeddings:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        vector = [0.0] * self.dimension
        counts = Counter(tokenize(text))
        for token, weight in counts.items():
            index = self._stable_hash(token) % self.dimension
            sign = -1.0 if self._stable_hash(f"{token}:sign") % 2 else 1.0
            vector[index] += sign * float(weight)

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    @staticmethod
    def _stable_hash(value: str) -> int:
        digest = hashlib.sha256(value.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=False)


class HybridKnowledgeBase:
    def __init__(
        self,
        root_dirs: List[str],
        include_globs: List[str],
        *,
        chunk_size: int = 900,
        chunk_overlap: int = 120,
        persist_dir: str = "data/chroma",
        collection_name: str = "agenticrag_kb",
        embedding_dimension: int = 384,
        retrieval_mode: str = "hybrid",
        max_document_chars: int = 12000,
    ):
        self.root_dirs = [Path(path) for path in root_dirs if Path(path).exists()]
        self.include_globs = include_globs or ["*.md", "*.txt", "*.py", "*.yaml", "*.yml"]
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.retrieval_mode = retrieval_mode
        self.max_document_chars = max_document_chars
        self.manifest_path = self.persist_dir / f"{collection_name}_manifest.json"
        self.embedding_model = HashEmbeddings(embedding_dimension)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", "\u3002", "\uff0c", ".", ",", " ", ""],
        )
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        self.documents: List[Dict[str, Any]] = []
        self._load_or_build()

    def search(
        self,
        query: str,
        limit: int = 5,
        *,
        prefer_documents: bool = True,
        include_code: bool = False,
        retrieval_mode: str | None = None,
    ) -> List[Dict[str, Any]]:
        mode = (retrieval_mode or self.retrieval_mode).lower()
        if not query.strip():
            return []

        candidates: List[Dict[str, Any]] = []
        if mode in {"vector", "hybrid"}:
            candidates.extend(self._vector_search(query, max(limit * 2, 6)))
        if mode in {"lexical", "hybrid"}:
            candidates.extend(self._lexical_search(query, max(limit * 2, 6)))

        merged: Dict[tuple[str, int], Dict[str, Any]] = {}
        query_tokens = set(tokenize(query))
        query_text = query.lower()

        for item in candidates:
            key = (item["source"], item["metadata"].get("chunk_index", -1))
            doc_tokens = set(tokenize(item["content"]))
            overlap = len(query_tokens.intersection(doc_tokens))
            score = float(item.get("similarity", 0.0))

            if prefer_documents and not item["metadata"].get("is_code"):
                score += 0.08
            if item["metadata"].get("is_code"):
                score -= 0.14
            if item["metadata"].get("extension") in {".md", ".txt"}:
                score += 0.05
            if "readme" in item["source"].lower() or "usage" in item["source"].lower():
                score += 0.08
            if not include_code and item["metadata"].get("is_code") and overlap < 2:
                score -= 0.22
            if any(token in query_text for token in ["\u4ee3\u7801", "code", "python", "bug"]) and item["metadata"].get("is_code"):
                score += 0.14

            enriched = {
                **item,
                "metadata": {
                    **item["metadata"],
                    "keyword_overlap": overlap,
                },
                "similarity": round(max(min(score, 1.0), 0.0), 4),
            }

            if key not in merged or enriched["similarity"] > merged[key]["similarity"]:
                merged[key] = enriched

        ranked = sorted(merged.values(), key=lambda doc: doc["similarity"], reverse=True)
        return ranked[:limit]

    def stats(self) -> Dict[str, Any]:
        return {
            "sources": len({doc["source"] for doc in self.documents}),
            "chunks": len(self.documents),
            "collection_name": self.collection_name,
            "persist_dir": str(self.persist_dir),
            "retrieval_mode": self.retrieval_mode,
            "embedding": "hash",
        }

    def rebuild(self) -> Dict[str, Any]:
        self._rebuild_collection()
        return self.stats()

    def _load_or_build(self) -> None:
        current_signature = self._build_signature()
        stored_signature = None
        if self.manifest_path.exists():
            try:
                stored_signature = json.loads(self.manifest_path.read_text(encoding="utf-8")).get("signature")
            except json.JSONDecodeError:
                stored_signature = None

        if stored_signature != current_signature:
            self._rebuild_collection()
            self.manifest_path.write_text(
                json.dumps({"signature": current_signature}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            self.documents = self._load_documents()

    def _rebuild_collection(self) -> None:
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        try:
            existing = self.collection.get(include=[])
            existing_ids = list(existing.get("ids", []))
            for start in range(0, len(existing_ids), 200):
                self.collection.delete(ids=existing_ids[start : start + 200])
        except Exception:
            self.collection = self.client.get_or_create_collection(name=self.collection_name)

        self.documents = self._load_documents()
        if not self.documents:
            return

        texts = [doc["content"] for doc in self.documents]
        embeddings = self.embedding_model.embed_documents(texts)
        self.collection.add(
            ids=[doc["id"] for doc in self.documents],
            documents=texts,
            metadatas=[doc["metadata"] for doc in self.documents],
            embeddings=embeddings,
        )

    def _iter_candidate_paths(self, root: Path) -> Iterable[Path]:
        paths = [root] if root.is_file() else (path for pattern in self.include_globs for path in root.rglob(pattern))
        for path in paths:
            # Runtime credentials, test fixtures and retired samples are not knowledge sources.
            excluded = {".git", ".venv", ".cache", "node_modules", "tests", "config", "screenshots", "ui-concepts"}
            if excluded.intersection(path.parts) or path.name.startswith(".env") or path.name == "demo-knowledge.md":
                continue
            yield path

    def _load_documents(self) -> List[Dict[str, Any]]:
        documents: List[Dict[str, Any]] = []
        seen: set[Path] = set()
        for root in self.root_dirs:
            for path in self._iter_candidate_paths(root):
                if path.is_dir() or path in seen:
                    continue
                seen.add(path)
                text = self._read_text(path)
                if not text:
                    continue
                trimmed = public_data(text[: self.max_document_chars])
                chunks = self.splitter.split_text(trimmed) or [trimmed]
                total_chunks = len(chunks)
                for index, chunk in enumerate(chunks):
                    metadata = {
                        "source": str(path),
                        "filename": path.name,
                        "extension": path.suffix.lower(),
                        "chunk_index": index,
                        "total_chunks": total_chunks,
                        "is_code": is_code_like(chunk, str(path)),
                    }
                    documents.append(
                        {
                            "id": self._make_chunk_id(path, index, chunk),
                            "content": chunk,
                            "source": str(path),
                            "metadata": metadata,
                        }
                    )
        return documents

    def _vector_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        if not self.documents:
            return []
        embedding = self.embedding_model.embed_query(query)
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(limit, max(len(self.documents), 1)),
            include=["documents", "metadatas", "distances"],
        )
        docs = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        items: List[Dict[str, Any]] = []
        for content, metadata, distance in zip(docs, metadatas, distances):
            if not metadata:
                continue
            similarity = round(max(0.0, 1.0 - float(distance or 0.0)), 4)
            items.append(
                {
                    "content": content,
                    "source": str(metadata.get("source", "unknown")),
                    "similarity": similarity,
                    "metadata": dict(metadata),
                }
            )
        return items

    def _lexical_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        query_tokens = Counter(tokenize(query))
        if not query_tokens:
            return []

        scored: List[Dict[str, Any]] = []
        for doc in self.documents:
            doc_tokens = Counter(tokenize(doc["content"]))
            overlap = len(set(query_tokens).intersection(doc_tokens))
            cosine = self._cosine_similarity(query_tokens, doc_tokens)
            if cosine <= 0 and overlap <= 0:
                continue
            score = cosine + overlap * 0.05
            scored.append(
                {
                    "content": doc["content"],
                    "source": doc["source"],
                    "similarity": round(min(score, 1.0), 4),
                    "metadata": dict(doc["metadata"]),
                }
            )

        scored.sort(key=lambda item: item["similarity"], reverse=True)
        return scored[:limit]

    def _build_signature(self) -> str:
        payload = {
            "roots": [str(path) for path in self.root_dirs],
            "patterns": self.include_globs,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "reader_version": 3,
            "max_document_chars": self.max_document_chars,
            "files": [
                {
                    "path": str(path),
                    "mtime": path.stat().st_mtime,
                    "size": path.stat().st_size,
                }
                for root in self.root_dirs
                for path in self._iter_candidate_paths(root)
                if path.exists() and path.is_file()
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _make_chunk_id(self, path: Path, index: int, chunk: str) -> str:
        payload = f"{path}:{index}:{len(chunk)}".encode("utf-8")
        return hashlib.sha1(payload).hexdigest()

    def _read_text(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".docx", ".doc"}:
            return self._read_docx(path)
        try:
            return path.read_text(encoding="utf-8").lstrip("\ufeff")
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="gbk").lstrip("\ufeff")
            except Exception:
                return ""
        except Exception:
            return ""

    def _read_docx(self, path: Path) -> str:
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        try:
            with zipfile.ZipFile(path) as zf:
                if "word/document.xml" not in zf.namelist():
                    return ""
                xml_content = zf.read("word/document.xml")
            root = ET.fromstring(xml_content)
            paragraphs: List[str] = []
            for p in root.iter(f"{ns}p"):
                texts: List[str] = []
                for t in p.iter(f"{ns}t"):
                    if t.text:
                        texts.append(t.text)
                if texts:
                    paragraphs.append("".join(texts))
            return "\n\n".join(paragraphs)
        except Exception:
            return ""

    @staticmethod
    def _cosine_similarity(left: Counter, right: Counter) -> float:
        intersection = set(left).intersection(right)
        numerator = sum(left[token] * right[token] for token in intersection)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if not left_norm or not right_norm:
            return 0.0
        return numerator / (left_norm * right_norm)
