"""
네이버 뉴스 검색 모듈.

개선사항:
  - API 반환 link(n.news.naver.com) → 파싱 가능한 URL로 정규화
  - originallink(언론사 원문)도 병행 저장
  - 실제 네이버 뉴스 탭 HTML 결과도 보조 수집원으로 병합
  - HTML 태그 제거
"""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from urllib.parse import urlencode, urlparse
import re

import httpx

from config import Settings

NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"
NAVER_NEWS_TAB = "https://search.naver.com/search.naver"
MAX_DISPLAY = 100


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str | None = None
    press: str | None = None
    description: str | None = None


def search_naver_news(keyword: str, settings: Settings) -> list[SearchResult]:
    """네이버 검색 API와 뉴스 탭 HTML을 병합해 키워드 관련 뉴스 수집."""
    if not settings.naver_client_id or not settings.naver_client_secret:
        print(f"  [ERROR] NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 없습니다.")
        return []

    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }

    results: list[SearchResult] = []
    seen: set[str] = set()
    start = 1
    pages_fetched = 0
    max_pages = max(1, settings.max_search_pages)

    with httpx.Client(timeout=settings.request_timeout, headers=headers) as client:
        while len(results) < settings.max_results_per_keyword and pages_fetched < max_pages:
            display = min(MAX_DISPLAY, settings.max_results_per_keyword - len(results))
            params = {
                "query": keyword,
                "display": display,
                "start": start,
                "sort": "date",
            }
            try:
                r = client.get(NAVER_NEWS_API, params=params)
                if r.status_code != 200:
                    print(f"  [API ERROR] {keyword}: status={r.status_code}, {r.text[:200]}")
                    break
                data = r.json()
            except Exception as exc:
                print(f"  [API ERROR] {keyword}: {exc}")
                break

            items = data.get("items", [])
            if not items:
                break
            pages_fetched += 1

            for item in items:
                naver_link = item.get("link", "")
                original_link = item.get("originallink", "")

                url = _best_article_url(naver_link, original_link)
                if not url or url in seen:
                    continue
                seen.add(url)

                title = _strip_html(item.get("title", ""))
                description = _strip_html(item.get("description", ""))
                results.append(SearchResult(url=url, title=title, press=None, description=description))

            total = data.get("total", 0)
            start += len(items)
            if start > min(total, 1000):
                break

    if settings.naver_html_search_enabled:
        html_results = _search_naver_news_tab(keyword, settings, seen)
        results.extend(html_results)
        if html_results:
            print(f"  [HTML-FALLBACK] {keyword}: +{len(html_results)} news-tab results")

    return results


def _search_naver_news_tab(
    keyword: str,
    settings: Settings,
    seen: set[str],
) -> list[SearchResult]:
    """실제 네이버 뉴스 탭 HTML에서 기사 URL을 보조 추출."""
    results: list[SearchResult] = []
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.6,en;q=0.5",
    }
    max_pages = max(0, settings.max_html_search_pages)
    if max_pages <= 0:
        return results

    with httpx.Client(timeout=settings.request_timeout, headers=headers, follow_redirects=True) as client:
        for page in range(max_pages):
            params = {
                "where": "news",
                "query": keyword,
                "sort": "1",
                "start": str(page * 10 + 1),
            }
            try:
                response = client.get(NAVER_NEWS_TAB, params=params)
                if response.status_code != 200:
                    print(f"  [HTML SEARCH ERROR] {keyword}: status={response.status_code}")
                    break
            except Exception as exc:
                print(f"  [HTML SEARCH ERROR] {keyword}: {exc}")
                break

            extracted = 0
            for url in _extract_article_urls_from_search_html(response.text or ""):
                normalized_key = _normalize_naver_url(url) or url
                if normalized_key in seen or url in seen:
                    continue
                seen.add(normalized_key)
                seen.add(url)
                results.append(SearchResult(url=url))
                extracted += 1
                if len(results) >= settings.max_results_per_keyword:
                    return results
            if extracted == 0:
                break

    return results


def _extract_article_urls_from_search_html(html: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"https?://[^\"'<>\\\s]+", html):
        url = _clean_search_url(match.group(0))
        if url and _looks_like_article_url(url):
            candidates.append(url)
    return list(dict.fromkeys(candidates))


def _clean_search_url(url: str) -> str:
    cleaned = unescape(url)
    cleaned = cleaned.replace("\\/", "/").replace("\\u0026", "&")
    cleaned = cleaned.rstrip(").,;]")
    return cleaned


def _normalize_naver_url(url: str) -> str | None:
    """
    n.news.naver.com/mnews/article/123/0001234567
    → n.news.naver.com/article/123/0001234567
    으로 변환 (mnews 제거).
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
        path = parsed.path
        # /mnews/article/ → /article/
        path = re.sub(r"^/mnews/", "/", path)
        # /amp/article/ → /article/
        path = re.sub(r"^/amp/", "/", path)
        return parsed._replace(path=path, query="", fragment="").geturl()
    except Exception:
        return url


def _best_article_url(naver_link: str, original_link: str) -> str | None:
    candidates = [
        _normalize_naver_url(naver_link),
        original_link,
        naver_link,
    ]
    for candidate in candidates:
        if candidate and _looks_like_article_url(candidate):
            return candidate
    return None


def _looks_like_article_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    if any(static_host in host for static_host in (
        "pstatic.net", "googleapis.com", "gstatic.com", "cdnjs.cloudflare.com",
        "developers.kakao.com", "cdn.coenworks.com",
    )):
        return False
    path = parsed.path.lower()
    if not path or path == "/":
        return False
    if path.rstrip("/") in {"/news", "/main", "/home", "/index", "/default.aspx"}:
        return False
    if "newstomato.com" in parsed.netloc.lower() and path.rstrip("/") in {"", "/default.aspx"}:
        return False
    if any(token in path for token in ("/search", "/ranking", "/section", "/category", "/video", "/rss")):
        return False
    if "/photo" in path and not re.search(r"\d{4,}", path):
        return False
    if re.search(r"\.(jpg|jpeg|png|gif|webp|mp4|pdf|css|js|ico|svg|woff2?|ttf|eot)$", path):
        return False
    if any(token in path for token in ("/css/", "/js/", "/scripts/", "/images/", "/template/")):
        return False
    return bool(re.search(r"\d{4,}|article|view|read|idx|no=", path + "?" + parsed.query))


def _strip_html(text: str) -> str:
    """<b>, </b> 등 HTML 태그 제거."""
    return re.sub(r"<[^>]+>", "", text).strip()
