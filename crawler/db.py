from __future__ import annotations

import hashlib
from typing import Any

from supabase import Client, create_client

from config import Settings


class NewsTrackerDB:
    def __init__(self, settings: Settings) -> None:
        self.client: Client = create_client(settings.supabase_url, settings.supabase_key)

    def get_active_keywords(self) -> list[str]:
        result = (
            self.client.table("keywords")
            .select("keyword")
            .eq("is_active", True)
            .order("keyword")
            .execute()
        )
        return sorted({row["keyword"] for row in (result.data or []) if row.get("keyword")})

    def ensure_keywords(self, keywords: list[str] | tuple[str, ...]) -> None:
        unique_keywords = sorted({keyword.strip() for keyword in keywords if keyword and keyword.strip()})
        if not unique_keywords:
            return

        self.client.table("keywords").upsert(
            [{"keyword": keyword, "is_active": True} for keyword in unique_keywords],
            on_conflict="keyword",
            ignore_duplicates=True,
        ).execute()

    def deactivate_keywords(self, keywords: list[str] | tuple[str, ...]) -> None:
        unique_keywords = sorted({keyword.strip() for keyword in keywords if keyword and keyword.strip()})
        if not unique_keywords:
            return
        for keyword in unique_keywords:
            self.client.table("keywords").update({"is_active": False}).eq("keyword", keyword).execute()

    def get_article_by_normalized_url(self, normalized_url: str) -> dict[str, Any] | None:
        result = (
            self.client.table("articles")
            .select("*")
            .eq("normalized_url", normalized_url)
            .limit(1)
            .execute()
        )
        return (result.data or [None])[0]

    def get_articles_by_normalized_urls(self, normalized_urls: list[str]) -> dict[str, dict[str, Any]]:
        unique_urls = list(dict.fromkeys(url for url in normalized_urls if url))
        if not unique_urls:
            return {}

        rows: list[dict[str, Any]] = []
        try:
            for index in range(0, len(unique_urls), 100):
                chunk = unique_urls[index:index + 100]
                result = (
                    self.client.table("articles")
                    .select("*")
                    .in_("normalized_url", chunk)
                    .execute()
                )
                rows.extend(result.data or [])
        except Exception as exc:
            print(f"[DB-WARN] batch article lookup failed, falling back to single lookups: {exc}")
            for url in unique_urls:
                row = self.get_article_by_normalized_url(url)
                if row:
                    rows.append(row)

        return {row["normalized_url"]: row for row in rows if row.get("normalized_url")}

    def get_latest_version(self, article_id: str) -> dict[str, Any] | None:
        result = (
            self.client.table("article_versions")
            .select("*")
            .eq("article_id", article_id)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        return (result.data or [None])[0]

    def list_articles_for_recheck(
        self,
        limit: int,
        group_index: int = 0,
        group_count: int = 1,
        candidate_pool: int = 800,
    ) -> list[dict[str, Any]]:
        fetch_limit = max(limit * max(1, group_count) * 4, candidate_pool, 100)
        columns = "id,url,normalized_url,press,last_keyword,first_seen_at,last_seen_at,current_version"
        recent_result = (
            self.client.table("articles")
            .select(columns)
            .eq("is_deleted", False)
            .order("first_seen_at", desc=True)
            .limit(fetch_limit)
            .execute()
        )
        stale_result = (
            self.client.table("articles")
            .select(columns)
            .eq("is_deleted", False)
            .order("last_seen_at", desc=False)
            .limit(fetch_limit)
            .execute()
        )
        deleted_result = (
            self.client.table("articles")
            .select(columns)
            .eq("is_deleted", True)
            .order("last_seen_at", desc=False)
            .limit(max(limit * max(1, group_count), 50))
            .execute()
        )

        by_id: dict[str, dict[str, Any]] = {}
        for row in (recent_result.data or []) + (stale_result.data or []) + (deleted_result.data or []):
            if row.get("id"):
                by_id[row["id"]] = row

        rows = list(by_id.values())
        if group_count <= 1:
            return rows
        normalized_index = group_index % group_count
        return [
            row for row in rows
            if _stable_group(row.get("id", ""), group_count) == normalized_index
        ]

    def create_article(self, article: dict[str, Any]) -> dict[str, Any]:
        result = self.client.table("articles").insert(article).execute()
        return result.data[0]

    def update_article(self, article_id: str, values: dict[str, Any]) -> None:
        self.client.table("articles").update(values).eq("id", article_id).execute()

    def create_version(self, version: dict[str, Any]) -> dict[str, Any]:
        result = self.client.table("article_versions").insert(version).execute()
        return result.data[0]

    def create_change(self, change: dict[str, Any]) -> None:
        self.client.table("article_changes").insert(change).execute()

    def create_crawler_run(self, values: dict[str, Any]) -> str | None:
        try:
            result = self.client.table("crawler_runs").insert(values).execute()
            row = (result.data or [None])[0]
            return row.get("id") if row else None
        except Exception as exc:
            print(f"[RUN-LOG-WARN] could not create crawler_runs row: {exc}")
            return None

    def finish_crawler_run(self, run_id: str | None, values: dict[str, Any]) -> None:
        if not run_id:
            return
        try:
            self.client.table("crawler_runs").update(values).eq("id", run_id).execute()
        except Exception as exc:
            print(f"[RUN-LOG-WARN] could not update crawler_runs row: {exc}")


def _stable_group(value: str, group_count: int) -> int:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % max(1, group_count)
