"""
네이버 뉴스 기사 수정 추적기 - 메인.

개선사항:
  - recheck: last_seen_at 내림차순 → 최근 기사도 재확인
  - article_changes unique 충돌 시 조용히 처리
  - 로그: [NEW] / [CHANGED] / [NO-CHANGE] / [SKIP-*] 명확히 출력
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from article_parser import ParsedArticle, fetch_article
from config import get_settings
from db import NewsTrackerDB
from diff_engine import detect_change, stable_hash
from image_hash import compute_image_hashes
from relevance import filter_by_relevance
from search import search_naver_news


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def version_payload(
    article_id: str,
    version: int,
    keyword: str,
    parsed: ParsedArticle,
    image_hashes: list[str],
) -> dict[str, Any]:
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


def process_result(
    db: NewsTrackerDB,
    keyword: str,
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
        if existing and not existing.get("is_deleted"):
            now = utc_now_iso()
            db.update_article(existing["id"], {
                "is_deleted": True,
                "deleted_at": now,
                "last_seen_at": now,
            })
            print(f"  [DELETED] {url}")
        return parsed.normalized_url

    # ── 3. 파싱 실패 (메인/섹션 페이지 등) ──────────────────
    if parsed.parse_quality == "failed":
        print(f"  [SKIP-QUALITY] 파싱 실패: {url}")
        return None

    # ── 4. Relevance filtering ────────────────────────────────
    effective_title = parsed.title or search_title
    if not filter_by_relevance(keyword, effective_title, parsed.content_plain):
        return None

    # ── 5. 이미지 해시 계산 ──────────────────────────────────
    image_hashes = compute_image_hashes(parsed.image_urls, settings)

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
                "last_keyword": keyword,
            })
            db.create_version(version_payload(article["id"], 1, keyword, parsed, image_hashes))
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
                version_payload(existing["id"], 1, keyword, parsed, image_hashes)
            )
            db.update_article(existing["id"], {
                "url": parsed.url,
                "press": parsed.press or existing.get("press"),
                "last_seen_at": now,
                "last_keyword": keyword,
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
            "is_deleted":    existing.get("is_deleted", False),
        },
        {
            "title":         parsed.title,
            "content_plain": parsed.content_plain,
            "image_urls":    parsed.image_urls,
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
        "last_keyword": keyword,
        "is_deleted": False,
        "deleted_at": None,
    }

    if change["has_meaningful_change"]:
        next_version = int(existing["current_version"]) + 1
        try:
            db.create_version(
                version_payload(existing["id"], next_version, keyword, parsed, image_hashes)
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


def main() -> None:
    settings = get_settings()
    db = NewsTrackerDB(settings)
    keywords = db.get_active_keywords()

    if not keywords:
        print("No active keywords found.")
        return

    print(f"키워드 {len(keywords)}개 처리 시작: {', '.join(keywords)}")

    total_new = 0
    total_changed = 0
    total_skipped = 0
    processed_urls: set[str] = set()

    for keyword in keywords:
        results = search_naver_news(keyword, settings)
        print(f"\n[{keyword}] 검색 결과: {len(results)}개")

        for result in results:
            try:
                normalized_url = process_result(
                    db, keyword, result.url, result.press, result.title, settings
                )
                if normalized_url:
                    if normalized_url not in processed_urls:
                        total_new += 1
                    processed_urls.add(normalized_url)
                else:
                    total_skipped += 1
            except Exception as exc:
                print(f"  [ERROR] {result.url}: {exc}")

    # ── Recheck: 최근 기사 우선 재확인 ──────────────────────
    print(f"\n[RECHECK] 기존 기사 재확인 (최대 {settings.max_recheck_articles}개)")
    rechecked = 0
    for article in db.list_articles_for_recheck(settings.max_recheck_articles):
        if article["normalized_url"] in processed_urls:
            continue
        try:
            normalized_url = process_result(
                db,
                article.get("last_keyword") or keywords[0],
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

    print(
        f"\n완료: 처리={total_new}, skip={total_skipped}, "
        f"recheck={rechecked}, 총={len(processed_urls)}"
    )


if __name__ == "__main__":
    main()
