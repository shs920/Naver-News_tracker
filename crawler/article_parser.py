from __future__ import annotations

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
    "\uc0ad\uc81c\ub41c \uae30\uc0ac",
    "\uc874\uc7ac\ud558\uc9c0 \uc54a\ub294 \uae30\uc0ac",
    "\uc11c\ube44\uc2a4\ud558\uc9c0 \uc54a\ub294 \uae30\uc0ac",
    "\ud398\uc774\uc9c0\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4",
    "\uae30\uc0ac\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4",
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
    "\uad00\ub828\uae30\uc0ac",
    "\uad00\ub828 \ub274\uc2a4",
    "\uad00\ub828\ub274\uc2a4",
    "\uad00\ub828 \ud0a4\uc6cc\ub4dc",
    "\uad00\ub828\ud0a4\uc6cc\ub4dc",
    "\uad00\ub828\uc885\ubaa9",
    "\uc885\ubaa9\ub274\uc2a4",
    "\ub9ce\uc774 \ubcf8 \uae30\uc0ac",
    "\ub9ce\uc774\ubcf8 \uae30\uc0ac",
    "\ub9ce\uc774 \ubcf8 \ub274\uc2a4",
    "\uc778\uae30\uae30\uc0ac",
    "\uc8fc\uc694\ub274\uc2a4",
    "\ucd94\ucc9c\uae30\uc0ac",
    "\ud5e4\ub4dc\ub77c\uc778",
    "\uc624\ub298\uc758 \uc8fc\uc694\ub274\uc2a4",
    "\uc139\uc158\ub274\uc2a4",
    "\uc804\uccb4\uae30\uc0ac",
    "\uae30\uc0ac\uc81c\ubcf4",
    "\uc800\uc791\uad8c\uc790",
    "\ubb34\ub2e8\uc804\uc7ac",
    "\uc7ac\ubc30\ud3ec \uae08\uc9c0",
    "Copyright",
    "copyright",
    "GAM -",
)

LOW_QUALITY_TEXT_MARKERS = (
    "\ud68c\uc6d0\uc5d0\uac8c\ub9cc \uc81c\uacf5\ub418\ub294 \ud2b9\ubcc4\ud55c \ucf58\ud150\uce20",
    "\ubb34\ub8cc \ud68c\uc6d0 \uac00\uc785 \ud6c4 \ubc14\ub85c \uc774\uc6a9\ud558\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4",
    "\ub85c\uadf8\uc778 \ud6c4 \uc774\uc6a9\ud558\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4",
    "\ub51c\uc0ac\uc774\ud2b8 \ud68c\uc6d0\uc5d0\uac8c\ub9cc \uc81c\uacf5",
    "\uad6d\ubbfc\uc131\uc7a5\ud380\ub4dc \uac04\uc811\ud22c\uc790 \ubd84\uc57c",
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
    return any(pattern.search(path) for pattern in NON_ARTICLE_PATH_PATTERNS)


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

    try:
        with httpx.Client(
            timeout=settings.request_timeout,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        ) as client:
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
    content_html, parse_quality = _extract_content(soup, html, press, title)
    content_plain = _clean_article_plain(_html_to_plain(content_html))

    if _is_low_quality_content(content_plain, final_url):
        print(f"  [SKIP-QUALITY] low quality article body: {url}")
        content_html = None
        content_plain = None
        parse_quality = "failed"

    image_urls = _extract_images(BeautifulSoup(content_html or "", "html.parser"), final_url)

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
    original_host = urlparse(original_url).netloc.lower()
    final = urlparse(final_url)
    return bool(original_host and final.netloc.lower() != original_host and final.path.rstrip("/") in {"", "/"})


def _extract_content(
    soup: BeautifulSoup,
    html: str,
    press: str | None,
    title: str | None,
) -> tuple[str | None, str]:
    selectors = _selectors_for_page(soup, press)
    candidates: list[tuple[int, str]] = []

    for selector in selectors:
        for node in soup.select(selector)[:3]:
            fragment = _clean_content_node(node)
            plain = _html_to_plain(fragment)
            score = _content_candidate_score(plain, title) - _fragment_noise_penalty(fragment)
            if score > 0:
                candidates.append((score, fragment))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1], "ok"

    try:
        summary = Document(html).summary(html_partial=True)
        fragment = _clean_content_node(BeautifulSoup(summary, "html.parser"))
        plain = _html_to_plain(fragment)
        if _content_candidate_score(plain, title) - _fragment_noise_penalty(fragment) > 0:
            return fragment, "readability"
    except Exception:
        pass

    return None, "failed"


def _selectors_for_page(soup: BeautifulSoup, press: str | None) -> list[str]:
    selectors: list[str] = []
    if press:
        for press_key, press_selectors in PRESS_SELECTORS.items():
            if press_key in press:
                selectors.extend(press_selectors)

    host = _page_host(soup)
    if "newspim.com" in host:
        selectors.extend(["#contents", "#article_content", ".view_cont", ".article_view", ".news_view"])
    if "kukinews.com" in host:
        selectors.extend(["#articleBody", "#article_body", ".article_body", ".view_content", ".news_body"])
    if "dealsite.co.kr" in host or "dealsitetv.com" in host:
        selectors.extend(["#articleBody", "#article_body", ".article_view", ".view_cont", ".article-body"])
    if "newdaily.co.kr" in host:
        selectors.extend(["#articleBody", "#article_body", ".article_view", ".news_view", ".article-body"])
    if "viva100.com" in host or "bridgenews" in host:
        selectors.extend(["#articleBody", "#article_body", ".article_view", ".article-body", ".view_con"])
    if "sentv.co.kr" in host:
        selectors.extend([".article_view", ".view_con", ".article-body", "#article_content", "article"])
    if "kpinews.kr" in host:
        selectors.extend([".view_con", ".article_view", "#article-view-content", ".article-body", "article"])
    if "newstomato.com" in host:
        selectors.extend(["#article_content", ".rns_text", ".article_view", ".view_con", "article"])

    selectors.extend(COMMON_SELECTORS)
    selectors.extend(["main article", "article"])
    return list(dict.fromkeys(selectors))


def _page_host(soup: BeautifulSoup) -> str:
    canonical = soup.select_one("link[rel='canonical']")
    og_url = soup.select_one("meta[property='og:url']")
    url = (
        (canonical.get("href") if canonical else None)
        or (og_url.get("content") if og_url else None)
        or ""
    )
    return urlparse(url).netloc.lower()


def _clean_content_node(node: Tag | BeautifulSoup) -> str:
    clone = BeautifulSoup(str(node), "html.parser")
    _remove_noise(clone)
    _remove_after_tail_markers(clone)
    return str(clone)


def _remove_noise(node: Tag | BeautifulSoup) -> None:
    selectors = list(NOISE_SELECTORS) + [
        "[class*='rank']", "[class*='best']", "[class*='issue']", "[class*='keyword']",
        "[class*='stock']", "[class*='relation']", "[id*='rank']", "[id*='best']",
        "[id*='keyword']", "[id*='stock']", "[id*='relation']",
    ]
    for selector in selectors:
        try:
            for tag in node.select(selector):
                tag.decompose()
        except Exception:
            pass


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
            sibling.extract()
        parent = current.parent
        current.extract()
        if parent is root or parent is None:
            break
        current = parent


def _content_candidate_score(plain: str | None, title: str | None) -> int:
    if not plain:
        return -1
    cleaned = _clean_article_plain(plain) or ""
    compact_length = len(re.sub(r"\s+", "", cleaned))
    if compact_length < MIN_CONTENT_LENGTH:
        return -1
    if _is_low_quality_content(cleaned, ""):
        return -1

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    short_headline_lines = sum(1 for line in lines if len(line) <= 45 and not line.endswith((".", "다", "요", "\"", "'")))
    score = compact_length - short_headline_lines * 80

    if title:
        title_tokens = {token for token in re.split(r"\W+", title.casefold()) if len(token) >= 2}
        body_tokens = {token for token in re.split(r"\W+", cleaned.casefold()) if len(token) >= 2}
        score += len(title_tokens & body_tokens) * 80

    return score


def _fragment_noise_penalty(fragment: str) -> int:
    soup = BeautifulSoup(fragment, "html.parser")
    plain = _html_to_plain(fragment) or ""
    compact_length = max(1, len(re.sub(r"\s+", "", plain)))
    link_text = " ".join(a.get_text(" ", strip=True) for a in soup.select("a"))
    link_ratio = len(re.sub(r"\s+", "", link_text)) / compact_length

    penalty = 0
    if link_ratio > 0.18:
        penalty += int(compact_length * link_ratio)

    image_count = len(soup.select("img"))
    paragraph_count = len([p for p in soup.select("p") if p.get_text(" ", strip=True)])
    if image_count >= 8 and paragraph_count <= 2:
        penalty += 400

    marker_hits = sum(1 for marker in ARTICLE_TAIL_MARKERS if marker in plain)
    penalty += marker_hits * 250
    return penalty


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


def _is_low_quality_content(content_plain: str | None, final_url: str) -> bool:
    if not content_plain:
        return True
    compact = re.sub(r"\s+", "", content_plain)
    if len(compact) < MIN_CONTENT_LENGTH:
        return True
    if final_url and is_non_article_url(final_url):
        return True
    if any(marker in content_plain for marker in LOW_QUALITY_TEXT_MARKERS):
        return True

    lines = [line.strip() for line in content_plain.splitlines() if line.strip()]
    number_only_lines = sum(1 for line in lines if re.fullmatch(r"\d{1,2}", line))
    if number_only_lines >= 5:
        return True
    tail_marker_hits = sum(1 for marker in ARTICLE_TAIL_MARKERS if marker in content_plain)
    if tail_marker_hits >= 4:
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
    if re.search(r"/(?:ad|banner|sns|share|rank|recommend|related|thumb)[_/.-]", lowered):
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
    lines = []
    for raw_line in text.splitlines():
        line = _strip_inline_noise(raw_line.strip())
        if line and not _is_noise_line(line):
            lines.append(line)
    text = "\n".join(lines)
    for marker in ARTICLE_TAIL_MARKERS:
        index = text.find(marker)
        if index > 0:
            text = text[:index].strip()
    return text or None


def _strip_inline_noise(line: str) -> str:
    line = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "", line)
    line = re.sub(r"\s{2,}", " ", line)
    return line.strip()


def _is_noise_line(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    if not compact:
        return True
    if any(token in compact for token in (
        "무단전재", "재배포금지", "저작권자", "Copyright", "기자페이지",
        "구독하기", "좋아요", "공유하기", "댓글", "관련기사", "많이본뉴스",
    )):
        return True
    if len(compact) <= 2 and compact.isdigit():
        return True
    return False


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", unescape(value)).strip()
    return value or None
