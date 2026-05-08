from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from article_parser import ParsedArticle, fetch_article
from config import get_settings
from db import NewsTrackerDB
from diff_engine import detect_change, stable_hash
from image_hash import compute_image_hashes
from search import search_naver_news


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def version_payload(article_id: str, version: int, keyword: str, parsed: ParsedArticle, image_hashes: list[str]) -> dict[str, Any]:
    return {
        "article_id": article_id,
        "version": version,
        "keyword": keyword,
        "title": parsed.title,
        "content": parsed.content,
        "content_plain": parsed.content_plain,
        "image_urls": parsed.image_urls,
        "image_hashes": image_hashes,
        "title_hash": stable_hash(parsed.title),
        "content_hash": stable_hash(parsed.content_plain),
        "fetched_at": utc_now_iso(),
    }


def comparable_current(parsed: ParsedArticle, image_hashes: list[str]) -> dict[str, Any]:
    return {
        "title": parsed.title,
        "content_plain": parsed.content_plain,
        "image_hashes": image_hashes,
        "is_deleted": parsed.is_deleted,
    }


def comparable_previous(version: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": version.get("title"),
        "content_plain": version.get("content_plain"),
        "image_hashes": version.get("image_hashes") or [],
        "is_deleted": article.get("is_deleted", False),
    }


def process_result(db: NewsTrackerDB, keyword: str, url: str, press: str | None, settings) -> str:
    parsed = fetch_article(url, press, settings)
    image_hashes = [] if parsed.is_deleted else compute_image_hashes(parsed.image_urls, settings)
    existing = db.get_article_by_normalized_url(parsed.normalized_url)
    now = utc_now_iso()

    if not existing:
        article = db.create_article(
            {
                "url": parsed.url,
                "normalized_url": parsed.normalized_url,
                "press": parsed.press,
                "source_type": "naver_news_search",
                "first_seen_at": now,
                "last_seen_at": now,
                "current_version": 1,
                "is_deleted": parsed.is_deleted,
                "deleted_at": now if parsed.is_deleted else None,
                "last_keyword": keyword,
            }
        )
        db.create_version(version_payload(article["id"], 1, keyword, parsed, image_hashes))
        return parsed.normalized_url

    latest = db.get_latest_version(existing["id"])
    if not latest:
        db.create_version(version_payload(existing["id"], existing.get("current_version", 1), keyword, parsed, image_hashes))
        db.update_article(
            existing["id"],
            {
                "url": parsed.url,
                "press": parsed.press or existing.get("press"),
                "last_seen_at": now,
                "last_keyword": keyword,
                "is_deleted": parsed.is_deleted,
                "deleted_at": now if parsed.is_deleted else None,
            },
        )
        return parsed.normalized_url

    change = detect_change(
        comparable_previous(latest, existing),
        comparable_current(parsed, image_hashes),
        title_threshold=settings.title_ratio_threshold,
        body_threshold=settings.body_ratio_threshold,
        image_threshold=settings.image_ratio_threshold,
        image_hamming_threshold=settings.image_hamming_threshold,
    )

    next_values = {
        "url": parsed.url,
        "press": parsed.press or existing.get("press"),
        "last_seen_at": now,
        "last_keyword": keyword,
        "is_deleted": parsed.is_deleted,
        "deleted_at": now if parsed.is_deleted and not existing.get("is_deleted") else existing.get("deleted_at"),
    }

    if change["has_meaningful_change"]:
        next_version = int(existing["current_version"]) + 1
        db.create_version(version_payload(existing["id"], next_version, keyword, parsed, image_hashes))
        db.create_change(
            {
                "article_id": existing["id"],
                "from_version": existing["current_version"],
                "to_version": next_version,
                "title_changed": change["title_changed"],
                "body_changed": change["body_changed"],
                "image_changed": change["image_changed"],
                "deleted_changed": change["deleted_changed"],
                "change_score": change["change_score"],
                "title_change_ratio": change["title_change_ratio"],
                "body_change_ratio": change["body_change_ratio"],
                "image_change_ratio": change["image_change_ratio"],
                "changed_at": now,
            }
        )
        next_values["current_version"] = next_version

    if not parsed.is_deleted:
        next_values["deleted_at"] = None

    db.update_article(existing["id"], next_values)
    return parsed.normalized_url


def main() -> None:
    settings = get_settings()
    db = NewsTrackerDB(settings)
    keywords = db.get_active_keywords()

    if not keywords:
        print("No active keywords found.")
        return

    total = 0
    processed_urls: set[str] = set()
    for keyword in keywords:
        results = search_naver_news(keyword, settings)
        print(f"{keyword}: {len(results)} search results")
        for result in results:
            try:
                normalized_url = process_result(db, keyword, result.url, result.press, settings)
                processed_urls.add(normalized_url)
                total += 1
            except Exception as exc:
                print(f"Failed: keyword={keyword} url={result.url} error={exc}")

    rechecked = 0
    for article in db.list_articles_for_recheck(settings.max_recheck_articles):
        if article["normalized_url"] in processed_urls:
            continue
        try:
            normalized_url = process_result(
                db,
                article.get("last_keyword") or "recheck",
                article["url"],
                article.get("press"),
                settings,
            )
            processed_urls.add(normalized_url)
            rechecked += 1
        except Exception as exc:
            print(f"Recheck failed: article_id={article['id']} url={article['url']} error={exc}")

    print(f"Processed {total} article candidates and rechecked {rechecked} tracked articles.")


if __name__ == "__main__":
    main()
