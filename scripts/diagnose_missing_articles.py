from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRAWLER_DIR = ROOT / "crawler"
sys.path.insert(0, str(CRAWLER_DIR))

from article_parser import normalize_url  # noqa: E402
from config import get_settings  # noqa: E402
from db import NewsTrackerDB  # noqa: E402
from relevance import filter_by_relevance  # noqa: E402
from search import search_naver_news  # noqa: E402


def selected_keywords(all_keywords: list[str]) -> list[str]:
    raw = os.environ.get("DIAG_KEYWORDS", "").strip()
    if not raw:
        return all_keywords
    requested = {keyword.strip() for keyword in raw.split(",") if keyword.strip()}
    return [keyword for keyword in all_keywords if keyword in requested]


def main() -> None:
    settings = get_settings()
    db = NewsTrackerDB(settings)
    db.ensure_keywords(settings.seed_keywords)

    all_keywords = db.get_active_keywords()
    keywords = selected_keywords(all_keywords)
    if not keywords:
        print("No keywords selected.")
        return

    total_seen = 0
    total_missing = 0
    total_irrelevant = 0

    for keyword in keywords:
        missing: list[tuple[str, str]] = []
        irrelevant = 0
        results = search_naver_news(keyword, settings)

        for result in results:
            total_seen += 1
            title = result.title or ""
            description = result.description or ""
            if not filter_by_relevance(keyword, title, description):
                irrelevant += 1
                total_irrelevant += 1
                continue

            normalized_url = normalize_url(result.url)
            if not db.get_article_by_normalized_url(normalized_url):
                missing.append((title, result.url))

        total_missing += len(missing)
        print(
            f"\n[{keyword}] api_results={len(results)} "
            f"missing_candidates={len(missing)} irrelevant_by_title_summary={irrelevant}"
        )
        for title, url in missing[:20]:
            print(f"  - {title[:90]} | {url}")

    print(
        f"\nSUMMARY keywords={len(keywords)}, api_results={total_seen}, "
        f"missing_candidates={total_missing}, irrelevant_by_title_summary={total_irrelevant}"
    )


if __name__ == "__main__":
    main()
