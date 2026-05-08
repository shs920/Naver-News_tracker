from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from readability import Document

from config import Settings


DELETED_PATTERNS = (
    "삭제된 기사",
    "존재하지 않는 기사",
    "서비스하지 않는 기사",
    "페이지를 찾을 수 없습니다",
    "요청하신 페이지를 찾을 수 없습니다",
    "기사를 찾을 수 없습니다",
)


@dataclass(frozen=True)
class ParsedArticle:
    url: str
    normalized_url: str
    final_url: str | None
    press: str | None
    title: str | None
    content: str | None
    content_plain: str | None
    image_urls: list[str]
    is_deleted: bool = False
    status_code: int | None = None


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid", "where", "query"}
    ]
    normalized_query = urlencode(sorted(query), doseq=True)
    return urlunparse(
        (
            parsed.scheme.lower() or "https",
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            "",
            normalized_query,
            "",
        )
    )


def fetch_article(url: str, fallback_press: str | None, settings: Settings) -> ParsedArticle:
    normalized_url = normalize_url(url)
    headers = {"User-Agent": settings.user_agent}

    try:
        with httpx.Client(timeout=settings.request_timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
    except httpx.HTTPError:
        return ParsedArticle(
            url=url,
            normalized_url=normalized_url,
            final_url=None,
            press=fallback_press,
            title=None,
            content=None,
            content_plain=None,
            image_urls=[],
            is_deleted=True,
            status_code=None,
        )

    final_url = str(response.url)
    html = response.text or ""
    deleted = is_deleted_response(response.status_code, html, url, final_url)

    if deleted:
        return ParsedArticle(
            url=url,
            normalized_url=normalized_url,
            final_url=final_url,
            press=fallback_press,
            title=None,
            content=None,
            content_plain=None,
            image_urls=[],
            is_deleted=True,
            status_code=response.status_code,
        )

    soup = BeautifulSoup(html, "html.parser")
    title = extract_title(soup, html)
    content_html = extract_content_html(soup, html)
    content_plain = html_to_plain_text(content_html)
    press = extract_press(soup) or fallback_press
    image_urls = extract_image_urls(soup)

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
    )


def is_deleted_response(status_code: int, html: str, original_url: str, final_url: str) -> bool:
    if status_code in {403, 404, 410}:
        return True

    plain = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    if any(pattern in plain for pattern in DELETED_PATTERNS):
        return True

    original_host = urlparse(original_url).netloc.lower()
    final = urlparse(final_url)
    final_host = final.netloc.lower()
    final_path = final.path.rstrip("/")

    if original_host and final_host and original_host != final_host and final_path in {"", "/"}:
        return True
    if final_path in {"", "/"} and "news" not in final_url.lower():
        return True

    return False


def extract_title(soup: BeautifulSoup, html: str) -> str | None:
    selectors = [
        "meta[property='og:title']",
        "meta[name='twitter:title']",
        "h2#title_area",
        "h1",
        "title",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get("content") if node.name == "meta" else node.get_text(" ", strip=True)
        value = clean_text(value)
        if value:
            return value

    try:
        return clean_text(Document(html).short_title())
    except Exception:
        return None


def extract_content_html(soup: BeautifulSoup, html: str) -> str | None:
    for selector in (
        "#dic_area",
        "#articeBody",
        "#articleBody",
        "article",
        ".article_body",
        ".newsct_article",
    ):
        node = soup.select_one(selector)
        if node:
            remove_noise(node)
            text = node.get_text(" ", strip=True)
            if len(text) > 80:
                return str(node)

    try:
        summary = Document(html).summary(html_partial=True)
        if html_to_plain_text(summary):
            return summary
    except Exception:
        pass

    body = soup.body
    if body:
        remove_noise(body)
        return str(body)
    return None


def remove_noise(node: BeautifulSoup) -> None:
    for tag in node.select("script, style, noscript, iframe, button, nav, aside, form"):
        tag.decompose()


def html_to_plain_text(content_html: str | None) -> str | None:
    if not content_html:
        return None
    soup = BeautifulSoup(content_html, "html.parser")
    text = soup.get_text("\n", strip=True)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


def extract_press(soup: BeautifulSoup) -> str | None:
    for selector in ("meta[property='og:article:author']", "meta[name='author']", ".media_end_head_top_logo img"):
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get("content") or node.get("alt") or node.get_text(" ", strip=True)
        value = clean_text(value)
        if value:
            return value
    return None


def extract_image_urls(soup: BeautifulSoup) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for node in soup.select("meta[property='og:image'], article img, #dic_area img, .article_body img"):
        url = node.get("content") or node.get("src") or node.get("data-src")
        if not url or url.startswith("data:") or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls[:20]


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", unescape(value)).strip()
    return value or None
