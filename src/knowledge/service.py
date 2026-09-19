"""SQLite job queue + one indexing worker. Uploads and chat never run PDF parsing inline."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from retrieval.hybrid_store import tokenize
from .embedding import Embedding, FINGERPRINT, MODEL, DIMENSION
from .parsing import validate, extract, split, SPLITTER

ACTIVE = ('queued', 'parsing', 'splitting', 'indexing')


class Cancelled(Exception):
    pass


class KnowledgeService:
    def __init__(self, root: Path, start_worker=True):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'files').mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.embed = Embedding(root)
        self._chroma = None
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS libraries (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL, created REAL NOT NULL,
                  deleted INTEGER NOT NULL DEFAULT 0, deleting INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS documents (
                  id TEXT PRIMARY KEY, kb_id TEXT NOT NULL, name TEXT NOT NULL, ext TEXT NOT NULL,
                  size INTEGER NOT NULL, sha TEXT NOT NULL, version TEXT NOT NULL, created REAL NOT NULL,
                  status TEXT NOT NULL, error TEXT, generation TEXT, fingerprint TEXT,
                  chunk_count INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS document_hash ON documents(kb_id,sha) WHERE deleted=0;
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL,
                  processed INTEGER NOT NULL DEFAULT 0, total INTEGER, error TEXT,
                  created REAL NOT NULL, updated REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS jobs_document ON jobs(doc_id,created);
                CREATE TABLE IF NOT EXISTS chunks (
                  id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, kb_id TEXT NOT NULL,
                  generation TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS chunks_library ON chunks(kb_id);
                PRAGMA user_version=1;
            ''')
            if 'deleting' not in {row[1] for row in db.execute('PRAGMA table_info(libraries)')}:
                db.execute('ALTER TABLE libraries ADD COLUMN deleting INTEGER NOT NULL DEFAULT 0')
            # No inference about work that never committed. Preserve previously active chunks.
            db.execute("UPDATE jobs SET status='failed', error='服务重启打断索引，请重试', updated=? WHERE action='index' AND status IN ('parsing','splitting','indexing')", (time.time(),))
            db.execute("UPDATE documents SET status=CASE WHEN generation IS NULL THEN 'failed' ELSE 'completed' END,error='服务重启打断索引，请重试' WHERE status IN ('parsing','splitting','indexing')")
            db.execute("UPDATE jobs SET status='queued' WHERE action='delete' AND status NOT IN ('completed','failed')")
        self.worker = None
        if start_worker:
            self.worker = threading.Thread(target=self._loop, name='knowledge-index', daemon=True)
            self.worker.start()

    @contextmanager
    def db(self):
        with self.lock:
            conn = sqlite3.connect(self.root / 'knowledge.sqlite3', timeout=15)
            conn.row_factory = sqlite3.Row
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.worker:
            self.worker.join(timeout=10)

    def libraries(self):
        with self.db() as db:
            return [dict(row) for row in db.execute('''SELECT l.*,
                (SELECT count(*) FROM documents d WHERE d.kb_id=l.id AND d.deleted=0) AS document_count,
                (SELECT count(*) FROM documents d WHERE d.kb_id=l.id AND d.deleted=0 AND d.status='completed') AS ready_count
                FROM libraries l WHERE deleted=0 ORDER BY created DESC''')]

    def library(self, kb_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM libraries WHERE id=? AND deleted=0', (kb_id,)).fetchone()
        if not row:
            raise LookupError('知识库不存在或已删除')
        return dict(row)

    def create(self, name, mode):
        key = uuid.uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO libraries(id,name,mode,created) VALUES(?,?,?,?)', (key, name, mode, time.time()))
        return self.library(key)

    def rename(self, kb_id, name):
        self.library(kb_id)
        with self.db() as db:
            db.execute('UPDATE libraries SET name=? WHERE id=? AND deleted=0', (name, kb_id))
        return self.library(kb_id)

    def _job(self, db, doc_id, action):
        now = time.time()
        db.execute('INSERT INTO jobs(id,doc_id,action,status,created,updated) VALUES(?,?,?,?,?,?)',
                   (uuid.uuid4().hex, doc_id, action, 'queued', now, now))

    def upload(self, kb_id, name, content):
        ext = validate(name, content)
        sha = hashlib.sha256(content).hexdigest()
        with self.db() as db:
            if self.library(kb_id)["deleting"]:
                raise ValueError("知识库正在删除，不能继续上传")
            duplicate = db.execute('SELECT id FROM documents WHERE kb_id=? AND sha=? AND deleted=0', (kb_id, sha)).fetchone()
            if duplicate:
                return {'document': self.document(kb_id, duplicate['id']), 'duplicate': True}
            key = uuid.uuid4().hex
            path = self.root / 'files' / key
            try:
                path.write_bytes(content)
                db.execute('''INSERT INTO documents(id,kb_id,name,ext,size,sha,version,created,status)
                    VALUES(?,?,?,?,?,?,?,?,?)''', (key, kb_id, name, ext, len(content), sha, sha, time.time(), 'queued'))
                self._job(db, key, 'index')
            except Exception:
                path.unlink(missing_ok=True)
                raise
        self.wake.set()
        return {'document': self.document(kb_id, key), 'duplicate': False}

    def document(self, kb_id, doc_id, include_deleted=False):
        with self.db() as db:
            row = db.execute('SELECT * FROM documents WHERE kb_id=? AND id=?', (kb_id, doc_id)).fetchone()
            if not row or (row['deleted'] and not include_deleted):
                raise LookupError('文档不存在或已删除；历史证据快照仍可查看')
            value = dict(row)
            job = db.execute('SELECT * FROM jobs WHERE doc_id=? ORDER BY created DESC,rowid DESC LIMIT 1', (doc_id,)).fetchone()
            value['job'] = dict(job) if job else None
            value['original_available'] = not value['deleted'] and (self.root / 'files' / value['id']).is_file()
            value['needs_rebuild'] = bool(value['generation'] and value['fingerprint'] != self.fingerprint(kb_id)) if not value['deleted'] else False
            return value

    def documents(self, kb_id):
        self.library(kb_id)
        with self.db() as db:
            rows = db.execute("SELECT id FROM documents WHERE kb_id=? AND (deleted=0 OR status IN ('deleting','delete_failed')) ORDER BY created DESC", (kb_id,)).fetchall()
            return [self.document(kb_id, row['id'], True) for row in rows]

    def fingerprint(self, kb_id):
        return SPLITTER if self.library(kb_id)['mode'] == 'keyword' else FINGERPRINT

    def retry(self, kb_id, doc_id):
        with self.db() as db:
            doc = self.document(kb_id, doc_id)
            if self.library(kb_id)["deleting"]:
                raise ValueError("知识库正在删除，不能重建索引")
            if doc['job'] and doc['job']['status'] in ACTIVE:
                return doc
            db.execute("UPDATE documents SET status=CASE WHEN generation IS NULL THEN 'queued' ELSE 'completed' END,error=NULL WHERE id=?", (doc_id,))
            self._job(db, doc_id, 'index')
        self.wake.set()
        return self.document(kb_id, doc_id)

    def cancel(self, kb_id, doc_id):
        with self.db() as db:
            self.document(kb_id, doc_id)
            db.execute("UPDATE jobs SET status='cancelled',updated=? WHERE doc_id=? AND action='index' AND status IN ('queued','parsing','splitting','indexing')", (time.time(), doc_id))
            db.execute("UPDATE documents SET status=CASE WHEN generation IS NULL THEN 'cancelled' ELSE 'completed' END WHERE id=?", (doc_id,))
        return self.document(kb_id, doc_id)

    def delete_document(self, kb_id, doc_id):
        with self.db() as db:
            doc = self.document(kb_id, doc_id, True)
            if doc['status'] in ('deleted', 'deleting'):
                return {'status': doc['status']}
            db.execute("UPDATE jobs SET status='cancelled',updated=? WHERE doc_id=? AND status IN ('queued','parsing','splitting','indexing')", (time.time(), doc_id))
            db.execute("UPDATE documents SET deleted=1,status='deleting',error=NULL WHERE id=?", (doc_id,))
            self._job(db, doc_id, 'delete')
        self.wake.set()
        return {'status': 'deleting'}

    def delete_library(self, kb_id):
        # Hide only after all original files/vectors have been removed. Failures remain actionable.
        with self.db() as db:
            self.library(kb_id)
            db.execute("UPDATE libraries SET deleting=1 WHERE id=?", (kb_id,))
            ids = [r['id'] for r in db.execute("SELECT id FROM documents WHERE kb_id=? AND status!='deleted'", (kb_id,))]
        for doc_id in ids:
            self.delete_document(kb_id, doc_id)
        with self.db() as db:
            if not ids:
                db.execute('UPDATE libraries SET deleted=1 WHERE id=?', (kb_id,))
                return {'status': 'deleted'}
        return {'status': 'deleting', 'message': '正在清理文档与索引，完成后知识库自动移除；清理失败可重试删除'}

    def _client(self):
        if self._chroma is None:
            import chromadb
            from chromadb.config import Settings
            self._chroma = chromadb.PersistentClient(path=str(self.root / 'vectors'), settings=Settings(anonymized_telemetry=False))
        return self._chroma

    def _collection(self):
        return self._client().get_or_create_collection('library-' + FINGERPRINT, embedding_function=None, metadata={'hnsw:space': 'cosine'})

    def _check(self, job_id):
        if self.stop.is_set():
            raise Cancelled()
        with self.db() as db:
            row = db.execute('SELECT j.status,d.deleted FROM jobs j JOIN documents d ON d.id=j.doc_id WHERE j.id=?', (job_id,)).fetchone()
        if not row or row['status'] == 'cancelled' or row['deleted']:
            raise Cancelled()

    def _stage(self, job, status, processed=0, total=None):
        with self.db() as db:
            self._check(job['id'])
            db.execute('UPDATE jobs SET status=?,processed=?,total=?,updated=? WHERE id=?', (status, processed, total, time.time(), job['id']))
            db.execute('UPDATE documents SET status=? WHERE id=? AND generation IS NULL', (status, job['doc_id']))

    def _loop(self):
        while not self.stop.is_set():
            if not self.process_next():
                self.wake.wait(1)
                self.wake.clear()

    def process_next(self):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY CASE action WHEN 'delete' THEN 0 ELSE 1 END,created LIMIT 1").fetchone()
        if not row:
            return False
        job = dict(row)
        collection, ids = None, []
        try:
            with self.db() as db:
                doc = dict(db.execute('SELECT * FROM documents WHERE id=?', (job['doc_id'],)).fetchone())
            if job['action'] == 'delete':
                if (self.root / 'vectors').exists():
                    for col in self._client().list_collections():
                        if col.name.startswith('library-'):
                            self._client().get_collection(col.name, embedding_function=None).delete(where={'document_id': doc['id']})
                (self.root / 'files' / doc['id']).unlink(missing_ok=True)
                with self.db() as db:
                    db.execute('DELETE FROM chunks WHERE doc_id=?', (doc['id'],))
                    db.execute("UPDATE documents SET status='deleted',chunk_count=0,generation=NULL,error=NULL WHERE id=?", (doc['id'],))
                    db.execute("UPDATE jobs SET status='completed',updated=? WHERE id=?", (time.time(), job['id']))
                    db.execute("UPDATE libraries SET deleted=1 WHERE id=? AND deleting=1 AND NOT EXISTS (SELECT 1 FROM documents WHERE kb_id=? AND status!='deleted')", (doc['kb_id'], doc['kb_id']))
                return True
            self._stage(job, 'parsing')
            pages = extract((self.root / 'files' / doc['id']).read_bytes(), doc['ext'], lambda: self._check(job['id']))
            self._stage(job, 'splitting')
            chunks = split(pages)
            if not chunks:
                raise ValueError('文档没有可索引的正文')
            kb = self.library(doc['kb_id'])
            generation = job['id']
            for index, chunk in enumerate(chunks):
                chunk['id'] = hashlib.sha256(f"{doc['id']}:{doc['version']}:{SPLITTER}:{index}".encode()).hexdigest()
            self._stage(job, 'indexing', 0, len(chunks))
            if kb['mode'] != 'keyword':
                collection = self._collection()
                for offset in range(0, len(chunks), 16):
                    self._check(job['id'])
                    batch = chunks[offset:offset + 16]
                    vectors = self.embed.encode([c['text'] for c in batch])
                    batch_ids = [generation + ':' + c['id'] for c in batch]
                    ids.extend(batch_ids)
                    collection.upsert(ids=batch_ids, embeddings=vectors,
                                      metadatas=[{'document_id': doc['id'], 'kb_id': kb['id'], 'generation': generation, 'chunk_id': c['id']} for c in batch])
                    self._stage(job, 'indexing', offset + len(batch), len(chunks))
            with self.db() as db:
                self._check(job['id'])
                db.execute('DELETE FROM chunks WHERE doc_id=?', (doc['id'],))
                db.executemany('INSERT INTO chunks(id,doc_id,kb_id,generation,content,metadata) VALUES(?,?,?,?,?,?)',
                               [(c['id'], doc['id'], kb['id'], generation, c['text'], json.dumps({k: v for k, v in c.items() if k not in ('id', 'text')}, ensure_ascii=False)) for c in chunks])
                db.execute("UPDATE documents SET status='completed',generation=?,fingerprint=?,chunk_count=?,error=NULL WHERE id=?", (generation, self.fingerprint(kb['id']), len(chunks), doc['id']))
                db.execute("UPDATE jobs SET status='completed',processed=?,total=?,updated=? WHERE id=?", (len(chunks), len(chunks), time.time(), job['id']))
            # Old/stale vectors are derived data. A failed cleanup cannot invalidate the committed generation.
            if collection:
                try:
                    collection.delete(where={'$and': [{'document_id': doc['id']}, {'generation': {'$ne': generation}}]})
                except Exception:
                    pass
        except Exception as exc:
            if collection and ids:
                try:
                    collection.delete(ids=ids)
                except Exception:
                    pass
            cancelled = isinstance(exc, Cancelled)
            error = None if cancelled else (str(exc) if isinstance(exc, ValueError) else '本地文件或索引操作失败，请重试并检查磁盘空间')
            with self.db() as db:
                db.execute('UPDATE jobs SET status=?,error=?,updated=? WHERE id=?', ('cancelled' if cancelled else 'failed', error, time.time(), job['id']))
                if job['action'] == 'delete':
                    db.execute("UPDATE documents SET status='delete_failed',error=? WHERE id=?", (error, job['doc_id']))
                else:
                    db.execute("UPDATE documents SET status=CASE WHEN generation IS NOT NULL THEN 'completed' ELSE ? END,error=? WHERE id=? AND deleted=0 AND ?=(SELECT id FROM jobs WHERE doc_id=? ORDER BY created DESC,rowid DESC LIMIT 1)", ('cancelled' if cancelled else 'failed', error, job['doc_id'], job['id'], job['doc_id']))
        return True

    def search(self, kb_id, query, limit=6, mode=None):
        kb = self.library(kb_id)
        if kb['deleting']:
            raise LookupError('知识库正在删除，不再参与检索')
        mode = mode or kb['mode']
        if mode not in {'keyword', 'semantic', 'hybrid'} or (mode != 'keyword' and kb['mode'] == 'keyword'):
            raise ValueError('此知识库只有关键词索引；语义模式须在创建知识库时启用')
        with self.db() as db:
            docs = db.execute('SELECT * FROM documents WHERE kb_id=? AND deleted=0', (kb_id,)).fetchall()
            rows = [dict(r) for r in db.execute("SELECT c.*,d.name,d.version FROM chunks c JOIN documents d ON c.doc_id=d.id WHERE c.kb_id=? AND d.deleted=0 AND d.status='completed' AND d.fingerprint=?", (kb_id, self.fingerprint(kb_id)))]
        state = 'ready' if rows else ('empty' if not docs else 'indexing' if any(d['status'] in ACTIVE for d in docs) else 'not_ready')
        if not rows:
            return {'documents': [], 'metadata': {'state': state, 'knowledge_base_id': kb_id, 'mode': mode}}
        counts = [Counter(tokenize(row['content'])) for row in rows]
        terms = set(tokenize(query))
        lengths = [sum(c.values()) for c in counts]
        average = sum(lengths) / len(lengths) or 1
        df = Counter(t for c in counts for t in c)
        scores = [sum(math.log(1 + (len(rows) - df[t] + .5) / (df[t] + .5)) * c[t] * 2.2 /
                      (c[t] + 1.2 * (.25 + .75 * lengths[i] / average)) for t in terms if c[t]) for i, c in enumerate(counts)]
        lexical = sorted((i for i in range(len(rows)) if scores[i] > 0), key=lambda i: scores[i], reverse=True)
        vector_order = []
        if mode != 'keyword':
            embedding = self.embed.encode([query], query=True)[0]
            # Query exactly committed IDs: staged, deleted and foreign documents cannot enter the candidate pool.
            generations = list({row['generation'] for row in rows})
            by_chunk = {row['id']: index for index, row in enumerate(rows)}
            result = self._collection().query(query_embeddings=[embedding], n_results=min(50, len(rows)),
                where={'$and': [{'kb_id': kb_id}, {'generation': {'$in': generations}}]},
                include=['metadatas', 'distances'])
            for metadata, distance in zip(result['metadatas'][0], result['distances'][0]):
                index = by_chunk.get(metadata['chunk_id'])
                if index is not None and 1 - distance >= .35:
                    vector_order.append(index)
        ranks = [lexical] if mode == 'keyword' else [vector_order] if mode == 'semantic' else [lexical, vector_order]
        fusion = Counter()
        for ranking in ranks:
            for rank, index in enumerate(ranking[:50]):
                fusion[index] += 1 / (60 + rank + 1)
        output = []
        for index, score in fusion.most_common(limit):
            row = rows[index]
            output.append({'content': row['content'], 'source': row['name'], 'score': round(score * 61 / len(ranks), 4),
                'metadata': {**json.loads(row['metadata']), 'kind': 'local_document', 'knowledge_base_id': kb_id,
                             'document_id': row['doc_id'], 'chunk_id': row['id'], 'version': row['version'],
                             'document_name': row['name'], 'original_available': True, 'retrieval_mode': mode,
                             'embedding_model': MODEL if mode != 'keyword' else None,
                             'embedding_dimension': DIMENSION if mode != 'keyword' else None, 'splitter': SPLITTER}})
        return {'documents': output, 'metadata': {'state': 'ready' if output else 'no_match', 'knowledge_base_id': kb_id, 'mode': mode, 'candidate_count': len(rows)}}

    def evidence(self, kb_id, doc_id, chunk_id):
        doc = self.document(kb_id, doc_id, True)
        with self.db() as db:
            row = db.execute('SELECT content,metadata FROM chunks WHERE id=? AND kb_id=? AND doc_id=?', (chunk_id, kb_id, doc_id)).fetchone()
        return {'original_available': doc['original_available'], 'document_name': doc['name'], 'version': doc['version'],
                'content': row['content'] if row else None, 'position': json.loads(row['metadata']) if row else None}


_service = None
_service_lock = threading.Lock()
def get_service():
    global _service
    with _service_lock:
        if _service is not None:
            return _service
        root = Path(os.getenv('AGENTICRAG_KNOWLEDGE_DIR', str(Path(__file__).resolve().parents[2] / 'data/knowledge')))
        _service = KnowledgeService(root)
    return _service
