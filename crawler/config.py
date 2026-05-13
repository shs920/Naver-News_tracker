import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    naver_client_id: str
    naver_client_secret: str
    request_timeout: float = 15.0
    max_results_per_keyword: int = 100      # API 1회 최대 100건
    max_search_pages: int = 2               # 페이지네이션 (start 이동)
    max_recheck_articles: int = 50
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
    # ── 변경 감지 임계값 ────────────────────────────────────
    title_ratio_threshold: float = 0.08
    body_ratio_threshold: float = 0.05
    image_ratio_threshold: float = 0.20
    image_hamming_threshold: int = 8


def get_settings() -> Settings:
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()
    naver_client_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
    naver_client_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()

    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")

    if not naver_client_id or not naver_client_secret:
        raise RuntimeError(
            "NAVER_CLIENT_ID and NAVER_CLIENT_SECRET must be set.\n"
            "https://developers.naver.com 에서 '검색' API 키를 발급하세요."
        )

    return Settings(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        naver_client_id=naver_client_id,
        naver_client_secret=naver_client_secret,
        request_timeout=float(os.environ.get("REQUEST_TIMEOUT", "15")),
        max_results_per_keyword=int(os.environ.get("MAX_RESULTS_PER_KEYWORD", "100")),
        max_recheck_articles=int(os.environ.get("MAX_RECHECK_ARTICLES", "50")),
        body_ratio_threshold=float(os.environ.get("BODY_RATIO_THRESHOLD", "0.05")),
        image_ratio_threshold=float(os.environ.get("IMAGE_RATIO_THRESHOLD", "0.20")),
    )
