"""
기사 파싱 모듈.
개선사항:
- 언론사별 CSS selector 우선 적용
- 노이즈(광고/추천기사/레이아웃) 강화 제거
- 300자 미만 본문은 파싱 실패로 처리
- canonical URL 정규화 강화
- 메인/섹션/랭킹 페이지 차단
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag
from readability import Document

from config import Settings
from press_selectors import (
    COMMON_SELECTORS,
    MIN_CONTENT_LENGTH,
    NOISE_SELECTORS,
    PRESS_SELECTORS,
)

# ── 삭제/비공개 기사 판단 패턴 ─────────────────────────────
DELETED_PATTERNS = (
    "삭제된 기사",
    "존재하지 않는 기사",
    "서비스하지 않는 기사",
    "페이지를 찾을 수 없습니다",
    "요청하신 페이지를 찾을 수 없습니다",
    "기사를 찾을 수 없습니다",
    "이 기사는 언론사가 삭제했습니다",
)

# 정규화 시 제거할 쿼리 파라미터
STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "sid", "input", "from", "isfrom",
    "campaign", "rss", "output", "cid", "ref", "referer",
    "clickTrack", "ito", "mc_cid", "mc_eid",
}

# 기사가 아닌 URL 패턴 (수집 차단)
NON_ARTICLE_PATH_PATTERNS = (
    re.compile(r"^/?$"),                          # 메인
    re.compile(r"/section/"),                     # 섹션
    re.compile(r"/category/"),                    # 카테고리
    re.compile(r"/ranking"),                      # 랭킹
    re.compile(r"/photo(?:/|$)"),                 # 포토
    re.compile(r"/live(?:/|$)"),                  # 라이브
    re.compile(r"/video(?:/|$)"),                 # 동영상
    re.compile(r"/tag/"),                         # 태그
    re.compile(r"/search"),                       # 검색
    re.compile(r"/rss"),                          # RSS
    re.compile(r"\.(jpg|jpeg|png|gif|mp4|pdf)$"), # 파일
)


@dataclass
class ParsedArticle:
    url: str
    normalized_url: str
    final_url: str | None
    press: str | None
    title: str | None
    content: str | None
    content_plain: str | None
    image_urls: list[str] = field(default_factory=list)
    is_deleted: bool = False
    status_code: int | None = None
    parse_quality: str = "ok"  # ok | low_quality | failed


def is_non_article_url(url: str) -> bool:
    """기사가 아닌 메인/섹션/랭킹 등 URL 차단."""
    path = urlparse(url).path
    if "/photo" in path and re.search(r"\d{4,}", path):
        return False
    return any(p.search(path) for p in NON_ARTICLE_PATH_PATTERNS)


def normalize_url(url: str) -> str:
    """URL 정규화: 트래킹 파라미터 제거, 소문자, 경로 정리."""
    parsed = urlparse(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in STRIP_PARAMS
    ]
    normalized_query = urlencode(sorted(query), doseq=True)
    return urlunparse((
        parsed.scheme.lower() or "https",
        parsed.netloc.lower(),
        parsed.path.rstrip("/") or "/",
        "",
        normalized_query,
        "",
    ))


def fetch_article(url: str, fallback_press: str | None, settings: Settings) -> ParsedArticle:
    normalized_url = normalize_url(url)

    # 기사가 아닌 URL 사전 차단
    if is_non_article_url(url):
        print(f"  [SKIP] 비기사 URL: {url}")
        return _failed(url, normalized_url, fallback_press, status_code=None)

    headers = {"User-Agent": settings.user_agent}

    try:
        with httpx.Client(
            timeout=settings.request_timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        print(f"  [ERROR] HTTP 요청 실패: {url} → {exc}")
        return _failed(url, normalized_url, fallback_press, status_code=None)

    final_url = str(response.url)
    html = response.text or ""

    if response.status_code == 403:
        return _failed(url, normalized_url, fallback_press,
                       final_url=final_url, status_code=response.status_code)
    if _is_deleted_response(response.status_code, html, url, final_url):
        return _deleted(url, normalized_url, fallback_press,
                        final_url=final_url, status_code=response.status_code)
    if is_non_article_url(final_url):
        print(f"  [SKIP] redirect landed on non-article URL: {final_url}")
        return _failed(url, normalized_url, fallback_press,
                       final_url=final_url, status_code=response.status_code)

    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup, html)
    press = _extract_press(soup) or fallback_press
    content_html, parse_quality = _extract_content(soup, html, press)
    content_plain = _html_to_plain(content_html)
    if _is_low_quality_content(content_plain, title, final_url):
        print(f"  [SKIP-QUALITY] low quality article body: {url}")
        content_html = None
        content_plain = None
        parse_quality = "failed"
    content_soup = BeautifulSoup(content_html or "", "html.parser")
    image_urls = _extract_images(content_soup, soup)

    # 본문 품질 검사: 완전히 비어있는 경우만 failed 처리
    # (짧은 속보 기사 등은 정상 저장)
    if not content_plain or len(content_plain) < MIN_CONTENT_LENGTH:
        print(f"  [WARN] 본문 매우 짧음({len(content_plain or '')}자), 저장은 진행: {url}")

    return ParsedArticle(
        url=url,
        normalized_url=normalized_url,
        final_url=final_url,
        press=press,
        title=title,
        content=content_html,
        content_plain=content_plain,
        image_urls=image_urls,
        is_deleted=False,
        status_code=response.status_code,
        parse_quality=parse_quality,
    )


# ── 내부 헬퍼 ────────────────────────────────────────────

def _deleted(
    url: str, normalized_url: str, press: str | None,
    final_url: str | None = None, status_code: int | None = None,
) -> ParsedArticle:
    return ParsedArticle(
        url=url, normalized_url=normalized_url, final_url=final_url,
        press=press, title=None, content=None, content_plain=None,
        image_urls=[], is_deleted=True, status_code=status_code,
        parse_quality="failed",
    )


def _failed(
    url: str, normalized_url: str, press: str | None,
    final_url: str | None = None, status_code: int | None = None,
) -> ParsedArticle:
    return ParsedArticle(
        url=url, normalized_url=normalized_url, final_url=final_url,
        press=press, title=None, content=None, content_plain=None,
        image_urls=[], is_deleted=False, status_code=status_code,
        parse_quality="failed",
    )


def _is_deleted_response(
    status_code: int, html: str, original_url: str, final_url: str
) -> bool:
    if status_code in {404, 410}:
        return True

    plain = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    if any(p in plain for p in DELETED_PATTERNS):
        return True

    orig_host = urlparse(original_url).netloc.lower()
    final = urlparse(final_url)
    final_host = final.netloc.lower()
    final_path = final.path.rstrip("/")

    # 다른 호스트 메인 페이지로 리다이렉트 → 삭제로 판단
    if orig_host and final_host and orig_host != final_host and final_path in {"", "/"}:
        return True
    if final_path in {"", "/"}:
        return True

    return False


def _remove_noise(node: Tag) -> None:
    """광고, 추천기사, SNS, 댓글 등 노이즈 요소 제거."""
    for selector in NOISE_SELECTORS:
        try:
            for tag in node.select(selector):
                tag.decompose()
        except Exception:
            pass


def _extract_content(
    soup: BeautifulSoup, html: str, press: str | None
) -> tuple[str | None, str]:
    """
    우선순위:
    1. 언론사 전용 selector
    2. 공통 selector
    3. readability fallback
    """
    # 1. 언론사 전용 selector
    if press:
        for press_key, selectors in PRESS_SELECTORS.items():
            if press_key in press:
                for sel in selectors:
                    node = soup.select_one(sel)
                    if node:
                        _remove_noise(node)
                        text = node.get_text(" ", strip=True)
                        if len(text) >= MIN_CONTENT_LENGTH:
                            return str(node), "ok"

    # 2. 공통 selector
    for sel in COMMON_SELECTORS:
        node = soup.select_one(sel)
        if node:
            _remove_noise(node)
            text = node.get_text(" ", strip=True)
            if len(text) >= MIN_CONTENT_LENGTH:
                return str(node), "ok"

    # 3. readability fallback
    try:
        summary = Document(html).summary(html_partial=True)
        plain = _html_to_plain(summary)
        if plain and len(plain) >= MIN_CONTENT_LENGTH:
            return summary, "readability"
    except Exception:
        pass

    return None, "failed"


def _extract_title(soup: BeautifulSoup, html: str) -> str | None:
    selectors = [
        "meta[property='og:title']",
        "meta[name='twitter:title']",
        "h2#title_area span",
        "h2#title_area",
        "h1.title",
        "h1",
        "title",
    ]
    for sel in selectors:
        node = soup.select_one(sel)
        if not node:
            continue
        value = node.get("content") if node.name == "meta" else node.get_text(" ", strip=True)
        value = _clean(value)
        if value:
            return value
    try:
        return _clean(Document(html).short_title())
    except Exception:
        return None


def _extract_press(soup: BeautifulSoup) -> str | None:
    for sel in (
        "meta[property='og:article:author']",
        "meta[name='author']",
        ".media_end_head_top_logo img",
        ".press_logo img",
        "[class*='press'] img",
    ):
        node = soup.select_one(sel)
        if not node:
            continue
        value = (
            node.get("content") or node.get("alt") or node.get_text(" ", strip=True)
        )
        value = _clean(value)
        if value:
            return value
    return None


def _is_low_quality_content(content_plain: str | None, title: str | None, final_url: str) -> bool:
    if not content_plain:
        return True
    compact = re.sub(r"\s+", "", content_plain)
    if len(compact) < MIN_CONTENT_LENGTH:
        return True
    if is_non_article_url(final_url):
        return True
    noise_terms = (
        "관련기사",
        "많이본뉴스",
        "인기뉴스",
        "추천기사",
        "포토뉴스",
        "구독",
        "로그인",
        "회원가입",
        "전체기사",
        "뉴스레터",
    )
    if sum(content_plain.count(term) for term in noise_terms) >= 5:
        return True
    return False


def _extract_images(content_soup: BeautifulSoup, page_soup: BeautifulSoup) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    selectors = [
        "#dic_area img",
        ".article_body img",
        "article img",
        ".newsct_article img",
        "img",
    ]
    for sel in selectors:
        for node in content_soup.select(sel):
            url = node.get("content") or node.get("src") or node.get("data-src")
            if not _is_valid_article_image_url(url, seen):
                continue
            # 아이콘/로고 제외 (작은 이미지 URL 패턴)
            seen.add(url)
            urls.append(url)
        if len(urls) >= 10:
            break
    if not urls:
        for node in page_soup.select("meta[property='og:image']"):
            url = node.get("content")
            if _is_valid_article_image_url(url, seen):
                seen.add(url)
                urls.append(url)
    return urls[:10]


def _is_valid_article_image_url(url: str | None, seen: set[str]) -> bool:
    if not url or url.startswith("data:") or url in seen:
        return False
    lowered = url.lower()
    if any(kw in lowered for kw in ("icon", "logo", "btn_", "button", "bullet", "blank", "profile", "avatar")):
        return False
    return True


def _html_to_plain(html: str | None) -> str | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", unescape(value)).strip()
    return value or None
