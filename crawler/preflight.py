from __future__ import annotations

import os
import sys

import httpx


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is empty or missing")
    return value


def _check_supabase(url: str, key: str) -> None:
    endpoint = f"{url.rstrip('/')}/rest/v1/crawler_runs"
    params = {"select": "id", "limit": "1"}
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    with httpx.Client(timeout=20) as client:
        response = client.get(endpoint, params=params, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Supabase REST check failed: status={response.status_code}, "
            f"body={response.text[:500]}"
        )


def _check_naver(client_id: str, client_secret: str) -> None:
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {"query": "빙그레", "display": "1", "start": "1", "sort": "date"}
    with httpx.Client(timeout=20, headers=headers) as client:
        response = client.get("https://openapi.naver.com/v1/search/news.json", params=params)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Naver Search API check failed: status={response.status_code}, "
            f"body={response.text[:500]}"
        )


def main() -> int:
    try:
        supabase_url = _require_env("SUPABASE_URL")
        supabase_key = _require_env("SUPABASE_KEY")
        naver_client_id = _require_env("NAVER_CLIENT_ID")
        naver_client_secret = _require_env("NAVER_CLIENT_SECRET")

        _check_supabase(supabase_url, supabase_key)
        print("Supabase REST check: OK")

        _check_naver(naver_client_id, naver_client_secret)
        print("Naver Search API check: OK")
        return 0
    except Exception as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
