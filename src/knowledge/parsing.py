"""Bounded text extraction; every chunk retains its actual original position."""
from __future__ import annotations

import io
import re
from pathlib import PurePath

MAX_FILES = 8
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = 32 * 1024 * 1024
MAX_TEXT = 2_000_000
SPLITTER = "paragraph-page-v1-420-60"


def validate(name: str, content: bytes) -> str:
    if not name or len(name) > 160 or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((' ', '.')):
        raise ValueError("文件名无效：请使用不含路径或特殊字符的短文件名")
    ext = PurePath(name).suffix.lower()
    if ext not in {'.txt', '.md', '.pdf'}:
        raise ValueError("仅支持 TXT、Markdown 和文本型 PDF")
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("文件不能为空，且单文件不得超过 10 MiB")
    if ext == '.pdf':
        if not content.startswith(b'%PDF-'):
            raise ValueError("文件内容不是 PDF")
    else:
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError("文本文件须使用 UTF-8 编码") from exc
        if not text.strip() or any(ord(c) < 32 and c not in '\n\r\t' for c in text):
            raise ValueError("文件包含二进制控制字符或没有文本")
        if text.lstrip().startswith(('%PDF-', 'MZ')):
            raise ValueError("扩展名与文件内容不一致")
    return ext


def extract(content: bytes, ext: str, check=lambda: None) -> list[dict]:
    if ext != '.pdf':
        text = content.decode('utf-8-sig')
        if len(text) > MAX_TEXT:
            raise ValueError("可解析文本超过 200 万字符，请拆分文档")
        return [{'page': None, 'text': text}]
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError("不支持加密 PDF，请先移除密码")
        if len(reader.pages) > 500:
            raise ValueError("PDF 最多支持 500 页")
        pages, total = [], 0
        for index, page in enumerate(reader.pages):
            check()
            text = page.extract_text() or ''
            total += len(text)
            if total > MAX_TEXT:
                raise ValueError("可解析文本超过 200 万字符，请拆分文档")
            pages.append({'page': index + 1, 'text': text})
        if not any(p['text'].strip() for p in pages):
            raise ValueError("PDF 没有可提取文字；扫描件需先进行 OCR，本系统不提供 OCR")
        return pages
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF 解析失败，请检查文件是否损坏或重新导出") from exc


def split(pages: list[dict]) -> list[dict]:
    chunks = []
    for page in pages:
        text, start, heading = page['text'], 0, ''
        headings = list(re.finditer(r'^#{1,6}\s+(.+)$', text, re.M))
        while start < len(text):
            end = min(start + 420, len(text))
            if end < len(text):
                boundary = max(text.rfind('\n', start + 200, end), text.rfind('。', start + 200, end))
                if boundary >= 0:
                    end = boundary + 1
            for match in headings:
                if match.start() <= start:
                    heading = match.group(1).strip()
            if text[start:end].strip():
                chunks.append({'text': text[start:end], 'page': page['page'], 'heading': heading,
                               'start': start, 'end': end})
            if end == len(text):
                break
            start = end - 60
    return chunks
