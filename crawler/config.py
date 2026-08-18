import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> None:
        return None

load_dotenv()

DEFAULT_SEED_KEYWORDS = (
    "빙그레,삼양식품,농심,CJ제일제당,오뚜기,오리온,롯데웰푸드,롯데칠성,"
    "대상,동원F&B,매일유업,남양유업,서울우유,하림,삼립,"
    "해태,hy,하이트진로,오비맥주,스타벅스,아워홈"
)
DEFAULT_DISCOVERY_EXCLUDED_KEYWORDS = "대상웰라이프,BBQ,BHC,교촌"
DEFAULT_RETIRED_KEYWORDS = "BBQ,BHC,교촌"


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    naver_client_id: str
    naver_client_secret: str
    request_timeout: float = 10.0
    max_results_per_keyword: int = 300
    max_search_pages: int = 3
    naver_html_search_enabled: bool = True
    max_html_search_pages: int = 3
    max_recheck_articles: int = 80
    recheck_candidate_pool: int = 800
    max_keywords_per_run: int = 0
    keyword_group_index: int = 0
    keyword_group_count: int = 1
    crawler_mode: str = "both"
    prefilter_search_results: bool = False
    discovery_recheck_existing: bool = False
    max_run_seconds: int = 0
    max_new_articles_per_keyword: int = 0
    max_images_per_article: int = 4
    seed_keywords: tuple[str, ...] = ()
    discovery_excluded_keywords: tuple[str, ...] = ()
    retired_keywords: tuple[str, ...] = ()
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
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
            "NAVER_CLIENT_ID and NAVER_CLIENT_SECRET must be set. "
            "Create Naver Search API credentials at https://developers.naver.com."
        )

    def env_bool(name: str, default: bool = False) -> bool:
        value = os.environ.get(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    return Settings(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        naver_client_id=naver_client_id,
        naver_client_secret=naver_client_secret,
        request_timeout=float(os.environ.get("REQUEST_TIMEOUT", "10")),
        max_results_per_keyword=int(os.environ.get("MAX_RESULTS_PER_KEYWORD", "300")),
        max_search_pages=int(os.environ.get("MAX_SEARCH_PAGES", "3")),
        naver_html_search_enabled=env_bool("NAVER_HTML_SEARCH_ENABLED", True),
        max_html_search_pages=int(os.environ.get("MAX_HTML_SEARCH_PAGES", "3")),
        max_recheck_articles=int(os.environ.get("MAX_RECHECK_ARTICLES", "80")),
        recheck_candidate_pool=int(os.environ.get("RECHECK_CANDIDATE_POOL", "800")),
        max_keywords_per_run=int(os.environ.get("MAX_KEYWORDS_PER_RUN", "0")),
        keyword_group_index=int(os.environ.get("KEYWORD_GROUP_INDEX", "0")),
        keyword_group_count=max(1, int(os.environ.get("KEYWORD_GROUP_COUNT", "1"))),
        crawler_mode=os.environ.get("CRAWLER_MODE", "both").strip().lower(),
        prefilter_search_results=env_bool("PREFILTER_SEARCH_RESULTS", False),
        discovery_recheck_existing=env_bool("DISCOVERY_RECHECK_EXISTING", False),
        max_run_seconds=int(os.environ.get("MAX_RUN_SECONDS", "0")),
        max_new_articles_per_keyword=int(os.environ.get("MAX_NEW_ARTICLES_PER_KEYWORD", "0")),
        max_images_per_article=int(os.environ.get("MAX_IMAGES_PER_ARTICLE", "4")),
        seed_keywords=tuple(
            keyword.strip()
            for keyword in os.environ.get("SEED_KEYWORDS", DEFAULT_SEED_KEYWORDS).split(",")
            if keyword.strip()
        ),
        discovery_excluded_keywords=tuple(
            keyword.strip()
            for keyword in os.environ.get(
                "DISCOVERY_EXCLUDED_KEYWORDS",
                DEFAULT_DISCOVERY_EXCLUDED_KEYWORDS,
            ).split(",")
            if keyword.strip()
        ),
        retired_keywords=tuple(
            keyword.strip()
            for keyword in os.environ.get("RETIRED_KEYWORDS", DEFAULT_RETIRED_KEYWORDS).split(",")
            if keyword.strip()
        ),
        title_ratio_threshold=float(os.environ.get("TITLE_RATIO_THRESHOLD", "0.08")),
        body_ratio_threshold=float(os.environ.get("BODY_RATIO_THRESHOLD", "0.05")),
        image_ratio_threshold=float(os.environ.get("IMAGE_RATIO_THRESHOLD", "0.20")),
        image_hamming_threshold=int(os.environ.get("IMAGE_HAMMING_THRESHOLD", "8")),
    )
