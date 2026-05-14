from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag
from readability import Document

from config import Settings
from press_selectors import COMMON_SELECTORS, MIN_CONTENT_LENGTH, NOISE_SELECTORS, PRESS_SELECTORS


DELETED_PATTERNS = (
    "삭제된 기사",
    "존재하지 않는 기사",
    "서비스하지 않는 기사",
    "페이지를 찾을 수 없습니다",
    "기사를 찾을 수 없습니다",
)

STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "sid", "input", "from", "isfrom",
    "campaign", "rss", "output", "cid", "ref", "referer",
    "clickTrack", "ito", "mc_cid", "mc_eid",
}

NON_ARTICLE_PATH_PATTERNS = (
    re.compile(r"^/?$"),
    re.compile(r"/(?:main|home|index)(?:\.html?|\.aspx)?/?$"),
    re.compile(r"/default\.aspx$"),
    re.compile(r"/section(?:/|$)"),
    re.compile(r"/category(?:/|$)"),
    re.compile(r"/ranking"),
    re.compile(r"/live(?:/|$)"),
    re.compile(r"/video(?:/|$)"),
    re.compile(r"/tag(?:/|$)"),
    re.compile(r"/search"),
    re.compile(r"/rss"),
    re.compile(r"\.(jpg|jpeg|png|gif|webp|mp4|pdf)$"),
)

ARTICLE_TAIL_MARKERS = (
    "[관련기사]",
    "[관련키워드]",
    "관련기사",
    "관련키워드",
    "저작권자",
    "무단 전재",
    "뒤로가기",
    "맨위로",
    "GAM - 해외주식",
    "뉴스핌 베스트 기사",
    "뉴스토마토 유튜브 라이브",
    "오늘의 라이브 편성표",
    "끝장뉴스",
    "뉴스in사이다",
    "많이 본 뉴스",
    "인기뉴스",
    "추천뉴스",
)

ARTICLE_START_MARKERS = (
    "[서울=뉴스핌]",
    "[서울=뉴스토마토]",
    "[서울경제TV=",
    "[서울=서울경제TV]",
    "[서울=뉴시스]",
    "[서울=뉴스1]",
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
    parse_quality: str = "ok"


def is_non_article_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if "/photo" in path and re.search(r"\d{4,}", path):
        return False
    if "newstomato.com" in host and path.rstrip("/") in {"", "/default.aspx"}:
        return True
    if any(pattern.search(path) for pattern in NON_ARTICLE_PATH_PATTERNS):
        return True
    return False


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in STRIP_PARAMS
    ]
    return urlunparse((
        parsed.scheme.lower() or "https",
        parsed.netloc.lower(),
        parsed.path.rstrip("/") or "/",
        "",
        urlencode(sorted(query), doseq=True),
        "",
    ))


def fetch_article(url: str, fallback_press: str | None, settings: Settings) -> ParsedArticle:
    normalized_url = normalize_url(url)

    if is_non_article_url(url):
        print(f"  [SKIP] non-article URL: {url}")
        return _failed(url, normalized_url, fallback_press)

    headers = {"User-Agent": settings.user_agent}
    try:
        with httpx.Client(timeout=settings.request_timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        print(f"  [ERROR] HTTP request failed: {url} - {exc}")
        return _failed(url, normalized_url, fallback_press)

    final_url = str(response.url)
    html = response.text or ""

    if response.status_code == 403:
        return _failed(url, normalized_url, fallback_press, final_url, response.status_code)
    if _is_deleted_response(response.status_code, html, url, final_url):
        return _deleted(url, normalized_url, fallback_press, final_url, response.status_code)
    if is_non_article_url(final_url):
        print(f"  [SKIP] redirect landed on non-article URL: {final_url}")
        return _failed(url, normalized_url, fallback_press, final_url, response.status_code)

    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup, html)
    press = _extract_press(soup) or fallback_press
    content_html, parse_quality = _extract_content(soup, html, press)
    content_plain = _clean_article_plain(_html_to_plain(content_html))

    if _is_low_quality_content(content_plain, title, final_url):
        print(f"  [SKIP-QUALITY] low quality article body: {url}")
        content_html = None
        content_plain = None
        parse_quality = "failed"

    content_soup = BeautifulSoup(content_html or "", "html.parser")
    image_urls = _extract_images(content_soup, final_url)

    if not content_plain or len(content_plain) < MIN_CONTENT_LENGTH:
        print(f"  [WARN] article body too short({len(content_plain or '')} chars): {url}")

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


def _deleted(
    url: str,
    normalized_url: str,
    press: str | None,
    final_url: str | None = None,
    status_code: int | None = None,
) -> ParsedArticle:
    return ParsedArticle(
        url=url,
        normalized_url=normalized_url,
        final_url=final_url,
        press=press,
        title=None,
        content=None,
        content_plain=None,
        image_urls=[],
        is_deleted=True,
        status_code=status_code,
        parse_quality="failed",
    )


def _failed(
    url: str,
    normalized_url: str,
    press: str | None,
    final_url: str | None = None,
    status_code: int | None = None,
) -> ParsedArticle:
    return ParsedArticle(
        url=url,
        normalized_url=normalized_url,
        final_url=final_url,
        press=press,
        title=None,
        content=None,
        content_plain=None,
        image_urls=[],
        is_deleted=False,
        status_code=status_code,
        parse_quality="failed",
    )


def _is_deleted_response(status_code: int, html: str, original_url: str, final_url: str) -> bool:
    if status_code in {404, 410}:
        return True

    plain = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    if any(pattern in plain for pattern in DELETED_PATTERNS):
        return True

    orig_host = urlparse(original_url).netloc.lower()
    final = urlparse(final_url)
    final_host = final.netloc.lower()
    final_path = final.path.rstrip("/")
    return bool(orig_host and final_host and orig_host != final_host and final_path in {"", "/"})


def _remove_noise(node: Tag) -> None:
    for selector in NOISE_SELECTORS:
        try:
            for tag in node.select(selector):
                tag.decompose()
        except Exception:
            pass


def _extract_content(soup: BeautifulSoup, html: str, press: str | None) -> tuple[str | None, str]:
    candidates: list[str] = []
    if press:
        for press_key, selectors in PRESS_SELECTORS.items():
            if press_key in press:
                candidates.extend(selectors)

    candidates.extend(_domain_selectors(soup))
    candidates.extend(COMMON_SELECTORS)

    for selector in candidates:
        node = soup.select_one(selector)
        if not node:
            continue
        html_fragment = _clean_content_node(node)
        plain = _html_to_plain(html_fragment)
        if plain and len(re.sub(r"\s+", "", plain)) >= MIN_CONTENT_LENGTH:
            return html_fragment, "ok"

    try:
        summary = Document(html).summary(html_partial=True)
        summary = _clean_content_node(BeautifulSoup(summary, "html.parser"))
        plain = _html_to_plain(summary)
        if plain and len(re.sub(r"\s+", "", plain)) >= MIN_CONTENT_LENGTH:
            return summary, "readability"
    except Exception:
        pass

    return None, "failed"


def _domain_selectors(soup: BeautifulSoup) -> list[str]:
    canonical = soup.select_one("link[rel='canonical']")
    og_url = soup.select_one("meta[property='og:url']")
    url = (
        (canonical.get("href") if canonical else None)
        or (og_url.get("content") if og_url else None)
        or ""
    )
    host = urlparse(url).netloc.lower()
    if "newspim.com" in host:
        return [
            "#contents",
            "#article_content",
            ".view_cont",
            ".article_view",
            ".news_view",
            ".view_text",
        ]
    if "sentv.co.kr" in host:
        return [".article_view", ".view_con", ".article-body", "#article_content", "article"]
    if "kpinews.kr" in host:
        return [".view_con", ".article_view", "#article-view-content", ".article-body", "article"]
    if "newstomato.com" in host:
        return ["#article_content", ".rns_text", ".article_view", ".view_con", "article"]
    return []


def _clean_content_node(node: Tag | BeautifulSoup) -> str:
    clone = BeautifulSoup(str(node), "html.parser")
    root = clone
    _remove_noise(root)
    _remove_after_tail_markers(root)
    return str(root)


def _remove_after_tail_markers(root: BeautifulSoup) -> None:
    for text_node in list(root.find_all(string=True)):
        text = str(text_node).strip()
        if not text or not any(marker in text for marker in ARTICLE_TAIL_MARKERS):
            continue
        _remove_node_and_following(text_node.parent if text_node.parent else text_node, root)
        break


def _remove_node_and_following(node: Tag | NavigableString, root: BeautifulSoup) -> None:
    current = node
    while current and current is not root:
        for sibling in list(current.next_siblings):
            if isinstance(sibling, Tag):
                sibling.decompose()
            else:
                sibling.extract()
        parent = current.parent
        current.extract()
        if parent is root or parent is None:
            break
        current = parent


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
    for selector in selectors:
        node = soup.select_one(selector)
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
    for selector in (
        "meta[property='og:article:author']",
        "meta[name='author']",
        ".media_end_head_top_logo img",
        ".press_logo img",
        "[class*='press'] img",
    ):
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get("content") or node.get("alt") or node.get_text(" ", strip=True)
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
        "관련기사", "많이 본 뉴스", "인기뉴스", "추천기사", "포토뉴스",
        "구독", "로그인", "회원가입", "전체기사", "뉴스레터",
    )
    if sum(content_plain.count(term) for term in noise_terms) >= 5:
        return True
    return False


def _extract_images(content_soup: BeautifulSoup, base_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for node in content_soup.select("img"):
        url = (
            node.get("data-src")
            or node.get("data-original")
            or node.get("data-lazy-src")
            or node.get("src")
            or node.get("content")
        )
        if not url:
            continue
        url = urljoin(base_url, url.strip())
        if not _is_valid_article_image_url(url, seen):
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= 10:
            break

    return urls


def _is_valid_article_image_url(url: str | None, seen: set[str]) -> bool:
    if not url or url.startswith("data:") or url in seen:
        return False
    lowered = url.lower()
    if any(token in lowered for token in (
        "icon", "logo", "btn_", "button", "bullet", "blank",
        "profile", "avatar", "sprite", "loading", "placeholder",
    )):
        return False
    if re.search(r"/(?:ad|banner|sns|share|rank|recommend|related)[_/.-]", lowered):
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


def _clean_article_plain(text: str | None) -> str | None:
    if not text:
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    for marker in ARTICLE_TAIL_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx].strip()

    starts = [text.find(marker) for marker in ARTICLE_START_MARKERS if text.find(marker) >= 0]
    if starts:
        text = text[min(starts):].strip()

    return text or None


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", unescape(value)).strip()
    return value or None
