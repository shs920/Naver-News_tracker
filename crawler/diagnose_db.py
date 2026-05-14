from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from supabase import create_client


TABLES = ("keywords", "articles", "article_versions", "article_changes")


def _count(client: Any, table: str) -> int | None:
    result = client.table(table).select("id", count="exact", head=True).execute()
    return result.count


def _latest_change(client: Any) -> dict[str, Any] | None:
    result = (
        client.table("article_changes")
        .select(
            """
            id, article_id, from_version, to_version,
            title_changed, body_changed, image_changed, deleted_changed,
            changed_at,
            articles ( id, url, press, last_keyword, is_deleted )
            """
        )
        .order("changed_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _version_title(client: Any, article_id: str, version: int) -> str | None:
    result = (
        client.table("article_versions")
        .select("title")
        .eq("article_id", article_id)
        .eq("version", version)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0].get("title") if rows else None


def _run(label: str, url: str, key: str) -> None:
    print(f"\n[{label}]")
    client = create_client(url, key)

    for table in TABLES:
        try:
            print(f"{table}: {_count(client, table)}")
        except Exception as exc:
            print(f"{table}: ERROR {exc}")

    try:
        change = _latest_change(client)
        if not change:
            print("latest_change: none")
            return

        title = _version_title(client, change["article_id"], int(change["to_version"]))
        print("latest_change:")
        print(f"  id={change['id']}")
        print(f"  article_id={change['article_id']}")
        print(f"  version={change['from_version']} -> {change['to_version']}")
        print(f"  changed_at={change['changed_at']}")
        print(f"  title={title or '(title not readable)'}")
    except Exception as exc:
        print(f"latest_change: ERROR {exc}")


def main() -> None:
    load_dotenv()

    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_KEY")
    anon_key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

    if not url:
        raise SystemExit("SUPABASE_URL or NEXT_PUBLIC_SUPABASE_URL is required.")
    if not service_key and not anon_key:
        raise SystemExit("SUPABASE_KEY or SUPABASE_ANON_KEY/NEXT_PUBLIC_SUPABASE_ANON_KEY is required.")

    if service_key:
        _run("service key", url, service_key)
    if anon_key:
        _run("anon key / frontend visibility", url, anon_key)


if __name__ == "__main__":
    main()
