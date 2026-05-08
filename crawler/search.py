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
    search_url = (
        "https://search.naver.com/search.naver"
        f"?where=news&query={quote_plus(keyword)}&sort=1"
    )
    headers = {"User-Agent": settings.user_agent}

    with httpx.Client(timeout=settings.request_timeout, follow_redirects=True, headers=headers) as client:
        response = client.get(search_url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[SearchResult] = []
    seen: set[str] = set()

    for item in soup.select("div.news_wrap, li.bx"):
        link = item.select_one("a.news_tit")
        if not link:
            continue

        raw_url = link.get("href")
        if not raw_url:
            continue

        url = unwrap_naver_redirect(raw_url)
        if url in seen:
            continue
        seen.add(url)

        press_node = item.select_one("a.info.press, span.info.press")
        press = press_node.get_text(" ", strip=True).replace("언론사 선정", "").strip() if press_node else None
        title = link.get("title") or link.get_text(" ", strip=True)
        results.append(SearchResult(url=url, title=title, press=press))

        if len(results) >= settings.max_results_per_keyword:
            break

    return results


def unwrap_naver_redirect(url: str) -> str:
    parsed = urlparse(url)
    if "naver.com" not in parsed.netloc:
        return url

    query = parse_qs(parsed.query)
    for key in ("url", "u"):
        if query.get(key):
            return query[key][0]
    return url
