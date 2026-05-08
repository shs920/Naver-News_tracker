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

    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.naver.com/",
    }

    with httpx.Client(
        timeout=settings.request_timeout,
        follow_redirects=True,
        headers=headers
    ) as client:
        response = client.get(search_url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    results: list[SearchResult] = []
    seen: set[str] = set()

    # 1차: 기존 네이버 뉴스 검색 구조
    selectors = [
        "a.news_tit",
        "a[href*='n.news.naver.com']",
        "a[href*='news.naver.com']",
        "a[href^='https://']",
    ]

    links = []

    for selector in selectors:
        found = soup.select(selector)
        if found:
            links.extend(found)

    for link in links:
        raw_url = link.get("href")
        if not raw_url:
            continue

        url = unwrap_naver_redirect(raw_url)

        if not is_probable_news_url(url):
            continue

        if url in seen:
            continue

        title = link.get("title") or link.get_text(" ", strip=True)

        if not title or len(title.strip()) < 5:
            continue

        seen.add(url)

        parent = link.find_parent()
        press = extract_press(parent)

        results.append(
            SearchResult(
                url=url,
                title=title.strip(),
                press=press
            )
        )

        if len(results) >= settings.max_results_per_keyword:
            break

    print(f"{keyword}: {len(results)} search results")

    if len(results) == 0:
        print("[검색 결과 0개] 네이버 HTML 구조 또는 접근 제한 가능성 있음")
        print("검색 URL:", search_url)
        print("응답 길이:", len(response.text))
        page_title = soup.title.get_text(strip=True) if soup.title else "title 없음"
        print("페이지 title:", page_title)

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


def is_probable_news_url(url: str) -> bool:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path.lower()

    if not url.startswith("http"):
        return False

    blocked_domains = [
        "search.naver.com",
        "www.naver.com",
        "kin.naver.com",
        "blog.naver.com",
        "cafe.naver.com",
        "shopping.naver.com",
        "adcr.naver.com",
        "nid.naver.com",
        "help.naver.com",
    ]

    for blocked in blocked_domains:
        if blocked in netloc:
            return False

    # 네이버 인링크 기사만 확실히 허용
    if "n.news.naver.com" in netloc:
        return True

    if "news.naver.com" in netloc and (
        "/article/" in path or "/mnews/article/" in path
    ):
        return True

    # 외부 언론사 메인/섹션/홈페이지는 우선 제외
    homepage_like_paths = [
        "",
        "/",
        "/news",
        "/main",
        "/home",
        "/index",
        "/index.html",
        "/article",
        "/articles",
    ]

    if path in homepage_like_paths:
        return False

    # 외부 언론사 기사 후보만 허용
    article_patterns = [
        "/news/",
        "/article/",
        "/articles/",
        "/view/",
        "/read/",
        "/detail/",
        "/newsview/",
        "/news_view/",
    ]

    if any(pattern in path for pattern in article_patterns):
        return True

    # 숫자 ID가 긴 URL은 기사일 가능성이 있음
    digits = "".join(ch for ch in path if ch.isdigit())
    if len(digits) >= 6:
        return True

    return False


def extract_press(parent) -> str | None:
    if not parent:
        return None

    press_selectors = [
        "a.info.press",
        "span.info.press",
        ".press",
        ".info_group",
        ".news_info",
    ]

    for selector in press_selectors:
        node = parent.select_one(selector)
        if node:
            text = node.get_text(" ", strip=True)
            text = text.replace("언론사 선정", "").strip()

            if text:
                return text

    return None
