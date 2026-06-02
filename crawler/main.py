"""
네이버 뉴스 기사 수정 추적기 - 메인.

개선사항:
  - recheck: last_seen_at 내림차순 → 최근 기사도 재확인
  - article_changes unique 충돌 시 조용히 처리
  - 로그: [NEW] / [CHANGED] / [NO-CHANGE] / [SKIP-*] 명확히 출력
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from article_parser import ParsedArticle, fetch_article, normalize_url as normalize_article_url
from config import get_settings
from db import NewsTrackerDB
from diff_engine import detect_change, stable_hash
from image_hash import compute_image_fingerprints
from relevance import filter_by_relevance, select_primary_keyword
from search import search_naver_news


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def select_keywords_for_run(
    keywords: list[str],
    max_keywords_per_run: int,
    group_index: int = 0,
    group_count: int = 1,
) -> list[str]:
    """Select a deterministic keyword shard for this crawler job."""
    if group_count > 1:
        normalized_index = group_index % group_count
        selected = [
            keyword
            for index, keyword in enumerate(keywords)
            if index % group_count == normalized_index
        ]
        return selected[:max_keywords_per_run] if max_keywords_per_run > 0 else selected

    if max_keywords_per_run <= 0 or max_keywords_per_run >= len(keywords):
        return keywords

    # GitHub Actions runs every 5 minutes. Advancing one slot per run covers all
    # keywords over several runs without repeatedly timing out on the full set.
    slot = int(datetime.now(timezone.utc).timestamp() // (5 * 60))
    start = (slot * max_keywords_per_run) % len(keywords)
    selected = keywords[start:start + max_keywords_per_run]
    if len(selected) < max_keywords_per_run:
        selected.extend(keywords[:max_keywords_per_run - len(selected)])
    return selected


def exclude_discovery_keywords(keywords: list[str], excluded_keywords: tuple[str, ...]) -> list[str]:
    excluded = {keyword.strip() for keyword in excluded_keywords if keyword and keyword.strip()}
    if not excluded:
        return keywords
    return [keyword for keyword in keywords if keyword not in excluded]


def parse_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def recheck_interval_minutes(first_seen_at: str | None) -> int:
    first_seen = parse_utc_datetime(first_seen_at)
    if not first_seen:
        return 30

    age_minutes = (datetime.now(timezone.utc) - first_seen).total_seconds() / 60
    if age_minutes <= 30:
        return 0
    if age_minutes <= 120:
        return 10
    if age_minutes <= 24 * 60:
        return 30
    if age_minutes <= 3 * 24 * 60:
        return 120
    return 360


def should_recheck_article(article: dict[str, Any]) -> bool:
    last_seen = parse_utc_datetime(article.get("last_seen_at"))
    if not last_seen:
        return True

    interval = recheck_interval_minutes(article.get("first_seen_at"))
    elapsed_minutes = (datetime.now(timezone.utc) - last_seen).total_seconds() / 60
    return elapsed_minutes >= interval


def version_payload(
    article_id: str,
    version: int,
    keyword: str,
    parsed: ParsedArticle,
    image_urls: list[str],
    image_hashes: list[str],
) -> dict[str, Any]:
    return {
        "article_id": article_id,
        "version": version,
        "keyword": keyword,
        "title": parsed.title,
        "content": parsed.content,
        "content_plain": parsed.content_plain,
        "image_urls": image_urls,
        "image_hashes": image_hashes,
        "title_hash": stable_hash(parsed.title),
        "content_hash": stable_hash(parsed.content_plain),
        "fetched_at": utc_now_iso(),
    }


def process_result(
    db: NewsTrackerDB,
    keyword: str,
    candidate_keywords: list[str],
    url: str,
    press: str | None,
    search_title: str | None,
    settings,
) -> str | None:
    """기사 1개 처리. 정상 처리 시 normalized_url 반환."""

    # ── 1. 파싱 ───────────────────────────────────────────────
    parsed = fetch_article(url, press, settings)

    # ── 2. 삭제 기사 처리 ────────────────────────────────────
    if parsed.is_deleted:
        existing = db.get_article_by_normalized_url(parsed.normalized_url)
        if existing and existing.get("is_deleted"):
            db.update_article(existing["id"], {"last_seen_at": utc_now_iso()})
            print(f"  [STILL-DELETED] {url}")
            return parsed.normalized_url

        if existing and not existing.get("is_deleted"):
            now = utc_now_iso()
            latest = db.get_latest_version(existing["id"])
            from_version = int(
                existing.get("current_version")
                or (latest.get("version") if latest else 1)
            )
            to_version = from_version + 1

            try:
                db.create_version({
                    "article_id": existing["id"],
                    "version": to_version,
                    "keyword": existing.get("last_keyword") or keyword,
                    "title": latest.get("title") if latest else None,
                    "content": None,
                    "content_plain": None,
                    "image_urls": [],
                    "image_hashes": [],
                    "title_hash": latest.get("title_hash") if latest else None,
                    "content_hash": stable_hash(""),
                    "fetched_at": now,
                })
            except Exception as exc:
                print(f"  [ERROR] 삭제 버전 저장 실패: {url} → {exc}")

            try:
                db.create_change({
                    "article_id": existing["id"],
                    "from_version": from_version,
                    "to_version": to_version,
                    "title_changed": False,
                    "body_changed": False,
                    "image_changed": False,
                    "deleted_changed": True,
                    "change_score": 1.0,
                    "title_change_ratio": 0,
                    "body_change_ratio": 0,
                    "image_change_ratio": 0,
                    "changed_at": now,
                })
            except Exception:
                pass

            db.update_article(existing["id"], {
                "is_deleted": True,
                "deleted_at": now,
                "last_seen_at": now,
                "current_version": to_version,
            })
            print(f"  [DELETED] v{to_version}: {url}")
        return parsed.normalized_url

    # ── 3. 파싱 실패 (메인/섹션 페이지 등) ──────────────────
    if parsed.parse_quality == "failed":
        print(f"  [SKIP-QUALITY] 파싱 실패: {url}")
        return None

    # ── 4. Relevance filtering ────────────────────────────────
    effective_title = parsed.title or search_title
    if not filter_by_relevance(keyword, effective_title, parsed.content_plain):
        existing = db.get_article_by_normalized_url(parsed.normalized_url)
        if existing:
            db.update_article(existing["id"], {"last_seen_at": utc_now_iso()})
            print(f"  [SKIP-RELEVANCE-EXISTING] {keyword}: {(effective_title or '')[:50]}")
        return None
    primary_keyword = select_primary_keyword(
        candidate_keywords,
        keyword,
        effective_title,
        parsed.content_plain,
    )
    if primary_keyword != keyword:
        print(f"  [PRIMARY-KEYWORD] {keyword} -> {primary_keyword}: {(effective_title or '')[:50]}")

    # ── 5. 이미지 해시 계산 ──────────────────────────────────
    image_urls, image_hashes = compute_image_fingerprints(parsed.image_urls, settings)

    now = utc_now_iso()
    existing = db.get_article_by_normalized_url(parsed.normalized_url)

    # ── 6. 신규 기사 저장 ────────────────────────────────────
    if not existing:
        try:
            article = db.create_article({
                "url": parsed.url,
                "normalized_url": parsed.normalized_url,
                "press": parsed.press,
                "source_type": "naver_news_api",
                "first_seen_at": now,
                "last_seen_at": now,
                "current_version": 1,
                "is_deleted": False,
                "deleted_at": None,
                "last_keyword": primary_keyword,
            })
            db.create_version(version_payload(article["id"], 1, primary_keyword, parsed, image_urls, image_hashes))
            print(f"  [NEW] v1 저장: {(effective_title or '')[:50]}")
        except Exception as exc:
            print(f"  [ERROR] 신규 저장 실패: {url} → {exc}")
        return parsed.normalized_url

    # ── 7. 기존 기사 변경 감지 ───────────────────────────────
    latest = db.get_latest_version(existing["id"])
    if not latest:
        # 버전 데이터 없으면 v1으로 저장
        try:
            db.create_version(
                version_payload(existing["id"], 1, primary_keyword, parsed, image_urls, image_hashes)
            )
            db.update_article(existing["id"], {
                "url": parsed.url,
                "press": parsed.press or existing.get("press"),
                "last_seen_at": now,
                "last_keyword": primary_keyword,
                "is_deleted": False,
                "deleted_at": None,
            })
        except Exception as exc:
            print(f"  [ERROR] 버전 저장 실패: {url} → {exc}")
        return parsed.normalized_url

    change = detect_change(
        {
            "title":         latest.get("title"),
            "content_plain": latest.get("content_plain"),
            "image_urls":    latest.get("image_urls") or [],
            "image_hashes":  latest.get("image_hashes") or [],
            "is_deleted":    False,
        },
        {
            "title":         parsed.title,
            "content_plain": parsed.content_plain,
            "image_urls":    image_urls,
            "image_hashes":  image_hashes,
            "is_deleted":    False,
        },
        title_threshold=settings.title_ratio_threshold,
        body_threshold=settings.body_ratio_threshold,
        image_threshold=settings.image_ratio_threshold,
        image_hamming_threshold=settings.image_hamming_threshold,
    )

    next_values: dict[str, Any] = {
        "url": parsed.url,
        "press": parsed.press or existing.get("press"),
        "last_seen_at": now,
        "last_keyword": primary_keyword,
        "is_deleted": False,
        "deleted_at": None,
    }

    if change["has_meaningful_change"]:
        next_version = int(existing["current_version"]) + 1
        try:
            db.create_version(
                version_payload(existing["id"], next_version, primary_keyword, parsed, image_urls, image_hashes)
            )
        except Exception as exc:
            print(f"  [ERROR] 버전 저장 실패: {url} → {exc}")
            db.update_article(existing["id"], next_values)
            return parsed.normalized_url

        try:
            db.create_change({
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
            })
        except Exception:
            # unique 제약 충돌(이미 같은 버전 변경 기록 존재) → 무시
            pass

        next_values["current_version"] = next_version
        changed_types = []
        if change["title_changed"]: changed_types.append("제목")
        if change["body_changed"]:  changed_types.append("본문")
        if change["image_changed"]: changed_types.append("사진")
        print(f"  [CHANGED] v{next_version} [{','.join(changed_types)}]: {(effective_title or '')[:50]}")
    else:
        print(f"  [NO-CHANGE] score={change['change_score']:.4f}: {(effective_title or '')[:50]}")

    db.update_article(existing["id"], next_values)
    return parsed.normalized_url


def run_discovery(
    db: NewsTrackerDB,
    keywords: list[str],
    all_keywords: list[str],
    settings,
    processed_urls: set[str],
) -> tuple[int, int]:
    print(
        f"DISCOVER keywords={len(keywords)}/{len(all_keywords)} "
        f"group={settings.keyword_group_index + 1}/{settings.keyword_group_count} "
        f"MAX_KEYWORDS_PER_RUN={settings.max_keywords_per_run}: "
        f"{', '.join(keywords)}"
    )
    processed = 0
    skipped = 0
    already_tracked = 0

    for keyword in keywords:
        results = search_naver_news(keyword, settings)
        print(f"\n[{keyword}] search results: {len(results)}")

        for result in results:
            try:
                if settings.prefilter_search_results and not filter_by_relevance(
                    keyword,
                    result.title,
                    getattr(result, "description", None),
                ):
                    skipped += 1
                    continue

                quick_normalized_url = normalize_article_url(result.url)
                existing = db.get_article_by_normalized_url(quick_normalized_url)
                if existing:
                    processed_urls.add(quick_normalized_url)
                    already_tracked += 1
                    if should_recheck_article(existing):
                        normalized_url = process_result(
                            db, keyword, all_keywords, result.url, result.press, result.title, settings
                        )
                        if normalized_url:
                            processed += 1
                    continue

                normalized_url = process_result(
                    db, keyword, all_keywords, result.url, result.press, result.title, settings
                )
                if normalized_url:
                    processed_urls.add(normalized_url)
                    processed += 1
                else:
                    skipped += 1
            except Exception as exc:
                print(f"  [ERROR] {result.url}: {exc}")

    print(f"DISCOVER already_tracked_skipped={already_tracked}")
    return processed, skipped


def run_recheck(
    db: NewsTrackerDB,
    fallback_keyword: str,
    all_keywords: list[str],
    settings,
    processed_urls: set[str],
) -> int:
    print(
        f"\n[RECHECK] candidates={settings.recheck_candidate_pool}, "
        f"limit={settings.max_recheck_articles}, "
        f"group={settings.keyword_group_index + 1}/{settings.keyword_group_count}"
    )
    rechecked = 0
    skipped_not_due = 0

    for article in db.list_articles_for_recheck(
        settings.max_recheck_articles,
        settings.keyword_group_index,
        settings.keyword_group_count,
        settings.recheck_candidate_pool,
    ):
        if rechecked >= settings.max_recheck_articles:
            break
        if article["normalized_url"] in processed_urls:
            continue
        if not should_recheck_article(article):
            skipped_not_due += 1
            continue

        try:
            normalized_url = process_result(
                db,
                article.get("last_keyword") or fallback_keyword,
                all_keywords,
                article["url"],
                article.get("press"),
                None,
                settings,
            )
            if normalized_url:
                processed_urls.add(normalized_url)
            rechecked += 1
        except Exception as exc:
            print(f"  [RECHECK ERROR] {article['url']}: {exc}")

    print(f"[RECHECK] done={rechecked}, skipped_not_due={skipped_not_due}")
    return rechecked


def main() -> None:
    settings = get_settings()
    mode = settings.crawler_mode
    if mode not in {"both", "discover", "recheck"}:
        raise RuntimeError("CRAWLER_MODE must be one of: both, discover, recheck")

    db: NewsTrackerDB | None = None
    run_log_id: str | None = None
    keywords_count = 0
    discovered = 0
    skipped = 0
    rechecked = 0

    try:
        db = NewsTrackerDB(settings)
        run_log_id = db.create_crawler_run({
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "mode": mode,
            "group_index": settings.keyword_group_index,
            "group_count": settings.keyword_group_count,
            "status": "running",
            "started_at": utc_now_iso(),
        })

        db.ensure_keywords(settings.seed_keywords)
        db.deactivate_keywords(settings.discovery_excluded_keywords)
        all_keywords = db.get_active_keywords()

        if not all_keywords:
            print("No active keywords found.")
            db.finish_crawler_run(run_log_id, {
                "status": "success",
                "finished_at": utc_now_iso(),
            })
            return

        discovery_keywords = exclude_discovery_keywords(
            all_keywords,
            settings.discovery_excluded_keywords,
        )
        keywords = select_keywords_for_run(
            discovery_keywords if mode in {"both", "discover"} else all_keywords,
            settings.max_keywords_per_run,
            settings.keyword_group_index,
            settings.keyword_group_count,
        )
        keywords_count = len(keywords)
        fallback_keyword = keywords[0] if keywords else all_keywords[0]
        processed_urls: set[str] = set()

        if mode in {"both", "discover"}:
            discovered, skipped = run_discovery(db, keywords, all_keywords, settings, processed_urls)

        if mode in {"both", "recheck"}:
            rechecked = run_recheck(db, fallback_keyword, all_keywords, settings, processed_urls)

        db.finish_crawler_run(run_log_id, {
            "status": "success",
            "finished_at": utc_now_iso(),
            "keywords_count": keywords_count,
            "processed_count": discovered,
            "skipped_count": skipped,
            "rechecked_count": rechecked,
        })

        print(
            f"\nDONE mode={mode}, discover_processed={discovered}, "
            f"skip={skipped}, recheck={rechecked}, unique_urls={len(processed_urls)}"
        )
    except Exception as exc:
        if db is not None:
            db.finish_crawler_run(run_log_id, {
                "status": "failed",
                "finished_at": utc_now_iso(),
                "keywords_count": keywords_count,
                "processed_count": discovered,
                "skipped_count": skipped,
                "rechecked_count": rechecked,
                "error_message": str(exc)[:1000],
            })
        raise


if __name__ == "__main__":
    main()
