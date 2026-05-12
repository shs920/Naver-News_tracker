import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    request_timeout: float = 15.0
    max_results_per_keyword: int = 30       # 20→30으로 확대
    max_search_pages: int = 2               # 검색 결과 페이지 수 (신규)
    max_recheck_articles: int = 50
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
    # ── 변경 감지 임계값 ────────────────────────────────────
    # 제목: 8% 이상 변경 시 감지 (기존 유지)
    title_ratio_threshold: float = 0.08
    # 본문: 5% 이상 변경 시 감지 (기존 3% → 5%로 상향, 오탈자 필터 강화)
    body_ratio_threshold: float = 0.05
    # 이미지: 20% 이상 변경 시 감지 (기존 1% → 20%, 오탐 차단)
    image_ratio_threshold: float = 0.20
    # pHash 해밍 거리: 8 이하면 동일 이미지 (기존 유지)
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
        max_results_per_keyword=int(os.environ.get("MAX_RESULTS_PER_KEYWORD", "30")),
        max_search_pages=int(os.environ.get("MAX_SEARCH_PAGES", "2")),
        max_recheck_articles=int(os.environ.get("MAX_RECHECK_ARTICLES", "50")),
        body_ratio_threshold=float(os.environ.get("BODY_RATIO_THRESHOLD", "0.05")),
        image_ratio_threshold=float(os.environ.get("IMAGE_RATIO_THRESHOLD", "0.20")),
    )
