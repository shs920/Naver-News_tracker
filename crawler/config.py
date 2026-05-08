import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    request_timeout: float = 15.0
    max_results_per_keyword: int = 20
    max_recheck_articles: int = 50
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
    title_ratio_threshold: float = 0.08
    body_ratio_threshold: float = 0.03
    image_ratio_threshold: float = 0.01
    image_hamming_threshold: int = 8


def get_settings() -> Settings:
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()

    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")

    return Settings(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        request_timeout=float(os.environ.get("REQUEST_TIMEOUT", "15")),
        max_results_per_keyword=int(os.environ.get("MAX_RESULTS_PER_KEYWORD", "20")),
        max_recheck_articles=int(os.environ.get("MAX_RECHECK_ARTICLES", "50")),
    )
