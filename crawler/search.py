"""
네이버 뉴스 검색 모듈 — 네이버 검색 API 사용.

개선사항:
  - API 반환 link(n.news.naver.com) → 파싱 가능한 URL로 정규화
  - originallink(언론사 원문)도 병행 저장
  - HTML 태그 제거
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs
import re

import httpx

from config import Settings

NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"
MAX_DISPLAY = 100


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str | None = None
    press: str | None = None


def search_naver_news(keyword: str, settings: Settings) -> list[SearchResult]:
    """네이버 검색 API로 키워드 관련 뉴스 수집."""
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

    with httpx.Client(timeout=settings.request_timeout, headers=headers) as client:
        while len(results) < settings.max_results_per_keyword:
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

            for item in items:
                naver_link = item.get("link", "")
                original_link = item.get("originallink", "")

                url = _best_article_url(naver_link, original_link)
                if not url or url in seen:
                    continue
                seen.add(url)

                title = _strip_html(item.get("title", ""))
                # description에서 언론사 추출 어려움 → press는 None으로
                results.append(SearchResult(url=url, title=title, press=None))

            total = data.get("total", 0)
            start += len(items)
            if start > min(total, 1000):
                break

    return results[:settings.max_results_per_keyword]


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
    path = parsed.path.lower()
    if not path or path == "/":
        return False
    if path.rstrip("/") in {"/news", "/main", "/home", "/index"}:
        return False
    if any(token in path for token in ("/search", "/ranking", "/section", "/category", "/video", "/rss")):
        return False
    if "/photo" in path and not re.search(r"\d{4,}", path):
        return False
    if re.search(r"\.(jpg|jpeg|png|gif|webp|mp4|pdf)$", path):
        return False
    return bool(re.search(r"\d{4,}|article|view|read|idx|no=", path + "?" + parsed.query))


def _strip_html(text: str) -> str:
    """<b>, </b> 등 HTML 태그 제거."""
    return re.sub(r"<[^>]+>", "", text).strip()
