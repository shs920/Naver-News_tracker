"""
네이버 뉴스 검색 모듈 — 네이버 검색 API 사용.

공식 API: https://openapi.naver.com/v1/search/news.json
- 서버 환경에서 차단 없음
- 하루 25,000건 무료
- 한 번 요청당 최대 100건
- sort=date: 최신순

GitHub Secrets 필요:
  NAVER_CLIENT_ID
  NAVER_CLIENT_SECRET
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs

import httpx

from config import Settings

NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"
MAX_DISPLAY = 100  # API 최대값


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str | None = None
    press: str | None = None


def search_naver_news(keyword: str, settings: Settings) -> list[SearchResult]:
    """
    네이버 검색 API로 키워드 관련 뉴스 기사 수집.
    max_results_per_keyword 개수까지 페이지네이션으로 수집.
    """
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
                    print(f"  [API ERROR] {keyword}: status={r.status_code}, {r.text[:100]}")
                    break
                data = r.json()
            except Exception as exc:
                print(f"  [API ERROR] {keyword}: {exc}")
                break

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                raw_url = item.get("originallink") or item.get("link", "")
                if not raw_url or raw_url in seen:
                    continue

                # 네이버 뉴스 URL로 변환 (originallink가 언론사 원문일 경우)
                # link는 항상 네이버 뉴스 URL
                naver_url = item.get("link", "")
                url = naver_url if naver_url else raw_url

                seen.add(url)
                title = _strip_html(item.get("title", ""))
                press = item.get("description", "")[:20] if item.get("description") else None

                results.append(SearchResult(url=url, title=title, press=press))

            # 다음 페이지
            total = data.get("total", 0)
            start += len(items)
            if start > min(total, 1000):  # API 최대 start=1000
                break

    return results[:settings.max_results_per_keyword]


def _strip_html(text: str) -> str:
    """네이버 API 반환값의 <b>, </b> 태그 제거."""
    return text.replace("<b>", "").replace("</b>", "").strip()
