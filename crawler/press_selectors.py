"""
언론사별 기사 본문 selector 정의.
우선순위: 언론사 전용 selector → 공통 selector → readability fallback
"""

# 언론사 이름(부분 일치) → CSS selector 목록
PRESS_SELECTORS: dict[str, list[str]] = {
    # 통신사
    "연합뉴스": ["#articleWrap .story-news article", "#articleWrap", ".story-news"],
    "뉴시스":   [".viewer_article", "#article_content"],
    "뉴스1":    [".news-article-content", "#articleBody"],

    # 종합일간지
    "조선일보": ["#fusion-app article", ".article-body", "#news_body_id"],
    "중앙일보": ["#article_body", ".article_body"],
    "동아일보": ["#article_txt", ".article_txt"],
    "한겨레":   ["#article-text", ".article-text", "#article_body"],
    "경향신문": ["#articleBody", ".art_body"],
    "한국일보": ["#articleText", ".article-text"],

    # 경제지
    "매일경제": ["#article_body", "#article_txt"],
    "한국경제": ["#articletxt", "#article_body"],
    "서울경제": ["#article_txt", ".article_view"],
    "파이낸셜뉴스": ["#articleBody"],
    "머니투데이": ["#textBody", "#newsEndContents"],
    "이데일리": ["#newsContentDiv", ".news_body"],
    "헤럴드경제": ["#articleText"],
    "아시아경제": ["#article_view"],

    # 방송
    "KBS":  [".content-view", "#cont-newstext"],
    "MBC":  ["#content article", ".news_txt"],
    "SBS":  ["#article_body_contents", ".article_body_contents"],
    "JTBC": ["#article-body", ".article_content"],
    "YTN":  ["#CmAdContent", ".content-article"],
    "채널A": ["#articleBody"],

    # 인터넷
    "오마이뉴스": ["#article_view_content"],
    "프레시안":   [".article-body"],
    "미디어오늘": [".article-body"],
}

# 공통 fallback selector (언론사 무관)
COMMON_SELECTORS: list[str] = [
    "#dic_area",
    "#articeBody",
    "#articleBody",
    "#articleBodyContents",
    ".go_trans._article_content",
    ".newsct_article",
    ".article_body",
    "article",
    ".article-body",
    ".news_body",
    "[itemprop='articleBody']",
]

# 제거할 노이즈 CSS selector
NOISE_SELECTORS: list[str] = [
    # 스크립트/스타일
    "script", "style", "noscript", "iframe",

    # 광고
    "[class*='ad']", "[id*='ad_']",
    "[class*='advertisement']", "[class*='sponsor']",
    "[class*='banner']", "[class*='promotion']",
    "[class*='adsense']", "[class*='adsbygoogle']",
    ".ad_wrap", ".ad_area", "#ad_area",

    # 추천/관련 기사
    "[class*='related']", "[class*='recommend']",
    "[class*='popular']", "[class*='ranking']",
    "[class*='most_view']", "[class*='most-view']",
    ".related_article", ".related_news",
    "#related_article",
    "[class*='more_news']", "[class*='another']",

    # SNS/공유
    "[class*='share']", "[class*='sns']",
    "[class*='social']", ".share_area",
    ".article_share", "#article_share",

    # 댓글
    "[class*='comment']", "[id*='comment']",
    "#comment", ".comment_area",

    # 기자 프로필
    "[class*='reporter']", "[class*='journalist']",
    ".reporter_area", ".reporter_info",

    # 저작권/푸터
    "[class*='copyright']", "[class*='copy_right']",
    "footer", "header", "nav", "aside",

    # 레이아웃
    "[class*='sidebar']",
    "[class*='widget']", "[class*='breadcrumb']",
    "[class*='pagination']",

    # 사진 슬라이드/갤러리
    "[class*='photo_slide']", "[class*='gallery']",
    "[class*='photo_area']",

    # 네이버 뉴스 전용 노이즈
    ".u_cbox", "#cbox_module",
    ".media_end_linked", ".media_end_bottom",
    ".NewsEndMain", ".byline",
    ".vod_area",

    # 버튼/폼
    "button", "form",
]

# 최소 본문 길이.
# 기사 수정 추적은 본문 품질이 중요하므로 광고/메뉴/짧은 오염 텍스트는 저장하지 않는다.
MIN_CONTENT_LENGTH = 80
