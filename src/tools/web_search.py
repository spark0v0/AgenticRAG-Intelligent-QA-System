"""Parallel public search adapters with partial-success and cancellable HTTP."""
import asyncio
import html
import re
import os
from urllib.parse import quote

import httpx
from .base import ToolDocument, ToolResult


SEARCH_ERRORS = {
    'not_configured': 'Tavily 尚未配置。请在后端 .env 设置 TAVILY_API_KEY，并重启服务。',
    'unauthorized': 'Tavily 凭据无效或无访问权限，请检查后端 TAVILY_API_KEY。',
    'quota': 'Tavily 请求受限或额度不足，请检查搜索服务账户后手动重试。',
    'timeout': '搜索服务响应超时，请检查网络后手动重试。',
    'unavailable': '搜索服务暂时不可用，请检查网络或服务状态后手动重试。',
    'invalid_response': '搜索服务返回了无法解析的数据，请稍后手动重试。',
    'no_results': '搜索已完成，但没有匹配的可用网页。请缩短问题并保留关键实体和时间。',
    'public_empty': '当前免费百科/即时答案搜索没有命中，它不覆盖完整网页。可在后端配置 Tavily 网页搜索。',
    'unsupported_provider': '搜索服务配置无效，WEB_SEARCH_PROVIDER 仅支持 tavily 或 public。',
}


def search_failure(reason: str, provider: str) -> ToolResult:
    return ToolResult(status='timeout' if reason == 'timeout' else 'error',
                      error=SEARCH_ERRORS[reason], metadata={'backend': provider, 'service': 'web', 'reason': reason})


async def search_web(query: str, limit: int, *, transport=None) -> ToolResult:
    key = os.getenv('TAVILY_API_KEY', '').strip()
    provider = os.getenv('WEB_SEARCH_PROVIDER', '').strip().lower() or ('tavily' if key else 'public')
    if provider == 'public':
        return await search_public(query, limit, transport=transport)
    if provider != 'tavily':
        return search_failure('unsupported_provider', provider='unknown')
    if not key:
        return search_failure('not_configured', 'tavily')
    try:
        async with httpx.AsyncClient(timeout=12, transport=transport) as client:
            response = await client.post('https://api.tavily.com/search',
                headers={'Authorization': f'Bearer {key}'},
                json={'query': query, 'max_results': max(1, min(limit, 8)), 'search_depth': 'basic',
                      'include_answer': False, 'include_raw_content': False})
            if response.status_code in (401, 403):
                return search_failure('unauthorized', 'tavily')
            if response.status_code in (429, 432, 433):
                return search_failure('quota', 'tavily')
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
            return search_failure('invalid_response', 'tavily')
        docs = {}
        for item in payload['results']:
            if not isinstance(item, dict):
                continue
            url, content = item.get('url'), item.get('content')
            if not isinstance(url, str) or not url.startswith(('https://', 'http://')) or not isinstance(content, str) or not content.strip():
                continue
            docs.setdefault(url, ToolDocument(content=content[:12000], source=url, score=0.7,
                metadata={'provider': 'tavily', 'title': str(item.get('title') or ''), 'evidence_kind': 'search_snippet'}))
        if not docs:
            return search_failure('no_results', 'tavily')
        return ToolResult(documents=list(docs.values())[:limit], metadata={
            'backend': 'tavily', 'service': 'web', 'coverage': 'web_search', 'partial': False})
    except httpx.TimeoutException:
        return search_failure('timeout', 'tavily')
    except httpx.HTTPError:
        return search_failure('unavailable', 'tavily')
    except ValueError:
        return search_failure('invalid_response', 'tavily')


async def search_public(query: str, limit: int, *, transport=None) -> ToolResult:
    headers = {'User-Agent': 'AgenticRAG/1.0 (local research workbench)'}
    async with httpx.AsyncClient(timeout=8, headers=headers, transport=transport, follow_redirects=True) as client:
        async def fetch(name, url, params):
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return name, response.json(), None
            except (httpx.HTTPError, ValueError) as exc:
                return name, {}, type(exc).__name__
        results = await asyncio.gather(
            fetch('duckduckgo', 'https://api.duckduckgo.com/',
                  {'q': query, 'format': 'json', 'no_html': 1, 'no_redirect': 1}),
            fetch('wikipedia', 'https://zh.wikipedia.org/w/api.php',
                  {'action': 'query', 'list': 'search', 'srsearch': query, 'srlimit': limit, 'format': 'json'}),
        )
    docs, errors = [], []
    for name, payload, error in results:
        if error or not isinstance(payload, dict):
            errors.append({'engine': name, 'error': error or 'InvalidResponse'})
            continue
        if name == 'wikipedia':
            for item in payload.get('query', {}).get('search', []):
                title = str(item.get('title', ''))
                excerpt = html.unescape(re.sub(r'<[^>]+>', '', item.get('snippet', '')))
                docs.append(ToolDocument(content=f'{title}：{excerpt}',
                    source='https://zh.wikipedia.org/wiki/' + quote(title.replace(' ', '_')),
                    score=0.7, metadata={'provider': name, 'title': title, 'evidence_kind': 'search_snippet'}))
        else:
            if payload.get('AbstractText') and payload.get('AbstractURL'):
                docs.append(ToolDocument(content=payload['AbstractText'], source=payload['AbstractURL'],
                    score=0.7, metadata={'provider': name, 'title': payload.get('Heading'), 'evidence_kind': 'abstract'}))
            topics = list(payload.get('RelatedTopics') or [])
            while topics and len(docs) < limit * 2:
                item = topics.pop(0)
                if not isinstance(item, dict):
                    continue
                topics.extend(item.get('Topics') or [])
                if item.get('Text') and item.get('FirstURL'):
                    docs.append(ToolDocument(content=item['Text'], source=item['FirstURL'], score=0.6,
                        metadata={'provider': name, 'evidence_kind': 'related_topic'}))
    unique = {}
    for doc in docs:
        if doc.source.startswith(('http://', 'https://')):
            unique.setdefault(doc.source, doc)
    return ToolResult(documents=list(unique.values())[:limit], status='success' if unique else 'error',
        error=None if unique else SEARCH_ERRORS['unavailable' if errors else 'public_empty'],
        metadata={'backend': 'public_search', 'service': 'web', 'engine_errors': errors,
                  'reason': None if unique else ('unavailable' if errors else 'public_empty'),
                  'partial': bool(unique and errors), 'coverage': 'encyclopedia_and_instant_answers_not_full_web'})
