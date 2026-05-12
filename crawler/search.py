"""
네이버 뉴스 검색 모듈.
개선: 페이지네이션으로 최대 max_search_pages 페이지까지 수집.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from config import Settings


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str | None = None
    press: str | None = None


def search_naver_news(keyword: str, settings: Settings) -> list[SearchResult]:
    headers = {"User-Agent": settings.user_agent}
    results: list[SearchResult] = []
    seen: set[str] = set()
    page_size = 10  # 네이버 검색 결과 기본 페이지당 10개

    with httpx.Client(
        timeout=settings.request_timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        for page in range(settings.max_search_pages):
            start = page * page_size + 1
            search_url = (
                "https://search.naver.com/search.naver"
                f"?where=news&query={quote_plus(keyword)}&sort=1&start={start}"
            )
            try:
                response = client.get(search_url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"  [SEARCH ERROR] {keyword} page={page+1}: {exc}")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            page_results = _parse_search_page(soup, seen, settings.max_results_per_keyword - len(results))

            results.extend(page_results)
            if len(results) >= settings.max_results_per_keyword:
                break
            if not page_results:
                break  # 더 이상 결과 없음

    return results


def _parse_search_page(
    soup: BeautifulSoup,
    seen: set[str],
    remaining: int,
) -> list[SearchResult]:
    results: list[SearchResult] = []
    for item in soup.select("div.news_wrap, li.bx"):
        if len(results) >= remaining:
            break
        link = item.select_one("a.news_tit")
        if not link:
            continue
        raw_url = link.get("href")
        if not raw_url:
            continue

        url = _unwrap_naver_redirect(raw_url)
        if url in seen:
            continue
        seen.add(url)

        press_node = item.select_one("a.info.press, span.info.press")
        press = (
            press_node.get_text(" ", strip=True).replace("언론사 선정", "").strip()
            if press_node else None
        )
        title = link.get("title") or link.get_text(" ", strip=True)
        results.append(SearchResult(url=url, title=title, press=press))

    return results


def _unwrap_naver_redirect(url: str) -> str:
    parsed = urlparse(url)
    if "naver.com" not in parsed.netloc:
        return url
    query = parse_qs(parsed.query)
    for key in ("url", "u"):
        if query.get(key):
            return query[key][0]
    return url
