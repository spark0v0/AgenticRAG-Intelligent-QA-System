"""Local document management API; never returns storage paths."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from typing import Literal

from api.providers import local_management
from knowledge.service import get_service
from knowledge.parsing import MAX_FILES, MAX_FILE_BYTES, MAX_REQUEST_BYTES, validate
from knowledge.embedding import MODEL, DIMENSION

router = APIRouter(prefix='/knowledge', dependencies=[Depends(local_management)])


class LibraryInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    mode: Literal['keyword', 'hybrid'] = 'keyword'

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError('知识库名称不能为空')
        return value.strip()


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal['keyword', 'semantic', 'hybrid'] | None = None


async def call(method, *args):
    try:
        return await asyncio.to_thread(method, *args)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, '知识库操作失败，请检查本地存储或稍后重试') from exc


@router.get('')
async def libraries():
    return {'items': await call(get_service().libraries), 'limits': {
        'files': MAX_FILES, 'file_bytes': MAX_FILE_BYTES, 'request_bytes': MAX_REQUEST_BYTES,
        'extensions': ['.txt', '.md', '.pdf']},
        'embedding': {'model': MODEL, 'dimensions': DIMENSION, 'download_mb': 90,
                      'runtime': 'CPU / ONNX，本地推理；需先下载模型'}}


@router.post('', status_code=201)
async def create(body: LibraryInput):
    return await call(get_service().create, body.name, body.mode)


@router.patch('/{kb_id}')
async def rename(kb_id: str, body: LibraryInput):
    return await call(get_service().rename, kb_id, body.name)


@router.delete('/{kb_id}', status_code=202)
async def delete_library(kb_id: str):
    return await call(get_service().delete_library, kb_id)


@router.get('/{kb_id}/documents')
async def documents(kb_id: str):
    return {'items': await call(get_service().documents, kb_id)}


@router.post('/{kb_id}/documents', status_code=202)
async def upload(kb_id: str, request: Request):
    # The ASGI middleware bounds the whole body, including multipart overhead/chunked uploads.
    async with request.form(max_files=MAX_FILES, max_fields=0, max_part_size=MAX_FILE_BYTES) as form:
        files = form.getlist('files')
        if not files or len(files) > MAX_FILES or len(form.multi_items()) != len(files):
            raise HTTPException(422, '每次请选择 1～8 个文件，字段名为 files')
        validated = []
        for file in files:
            # Starlette creates its UploadFile base class, not FastAPI's subclass.
            if not hasattr(file, 'read'):
                raise HTTPException(422, '上传字段必须是文件')
            content = await file.read(MAX_FILE_BYTES + 1)
            try:
                validate(file.filename or '', content)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            validated.append((file.filename, content))
        results = []
        for name, content in validated:
            results.append(await call(get_service().upload, kb_id, name, content))
        return {'items': results}


@router.post('/{kb_id}/documents/{doc_id}/retry', status_code=202)
async def retry(kb_id: str, doc_id: str):
    return await call(get_service().retry, kb_id, doc_id)


@router.post('/{kb_id}/documents/{doc_id}/cancel')
async def cancel(kb_id: str, doc_id: str):
    return await call(get_service().cancel, kb_id, doc_id)


@router.delete('/{kb_id}/documents/{doc_id}', status_code=202)
async def delete_document(kb_id: str, doc_id: str):
    return await call(get_service().delete_document, kb_id, doc_id)


@router.get('/{kb_id}/documents/{doc_id}/evidence/{chunk_id}')
async def evidence(kb_id: str, doc_id: str, chunk_id: str):
    return await call(get_service().evidence, kb_id, doc_id, chunk_id)


@router.get('/{kb_id}/documents/{doc_id}/original')
async def original(kb_id: str, doc_id: str):
    service = get_service()
    doc = await call(service.document, kb_id, doc_id, True)
    if not doc['original_available']:
        raise HTTPException(410, '原文已删除或不可用；历史回答保留当时的证据快照')
    return FileResponse(service.root / 'files' / doc['id'], filename=doc['name'],
                        media_type='application/pdf' if doc['ext'] == '.pdf' else 'text/plain; charset=utf-8',
                        content_disposition_type='inline', headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@router.post('/{kb_id}/search')
async def search(kb_id: str, body: SearchInput):
    return await call(get_service().search, kb_id, body.query, 6, body.mode)


class UploadLimitMiddleware:
    """Reject oversize uploads before multipart spooling, including requests without Content-Length."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or not scope['path'].startswith('/api/knowledge/') or not scope['path'].endswith('/documents'):
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        headers = dict(scope.get('headers', []))
        try:
            size = int(headers.get(b'content-length', b'0'))
        except ValueError:
            size = MAX_REQUEST_BYTES + 1
        chunks, total = [], 0
        if size <= MAX_REQUEST_BYTES:
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                total += len(message.get('body', b''))
                if total > MAX_REQUEST_BYTES:
                    break
                chunks.append(message)
                if not message.get('more_body'):
                    async def replay():
                        return chunks.pop(0) if chunks else await receive()
                    return await self.app(scope, replay, send)
        await JSONResponse({'detail': '单次上传请求不能超过 32 MiB（含表单封装）'}, status_code=413)(scope, receive, send)
