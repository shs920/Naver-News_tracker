from __future__ import annotations

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

    def get_article_by_normalized_url(self, normalized_url: str) -> dict[str, Any] | None:
        result = (
            self.client.table("articles")
            .select("*")
            .eq("normalized_url", normalized_url)
            .limit(1)
            .execute()
        )
        return (result.data or [None])[0]

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
    ) -> list[dict[str, Any]]:
        fetch_limit = limit * max(1, group_count)
        result = (
            self.client.table("articles")
            .select("id,url,normalized_url,press,last_keyword,last_seen_at")
            .eq("is_deleted", False)
            .order("last_seen_at", desc=True)
            .limit(fetch_limit)
            .execute()
        )
        rows = result.data or []
        if group_count <= 1:
            return rows[:limit]
        return rows[group_index::group_count][:limit]

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
