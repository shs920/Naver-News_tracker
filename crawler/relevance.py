"""
기업 relevance scoring.

점수 기준:
  alias 발견(본문):  +10
  alias 발견(제목):  +15  ← 제목 가중치
  required_context:  +3
  exclude_keyword:   -20
  alias 중복 발견:   중복 없이 alias당 1회만 카운트

MIN_RELEVANCE_SCORE 미만이면 skip.
"""
from __future__ import annotations

import re

from company_rules import COMPANY_RULES, MIN_RELEVANCE_SCORE


def _count_matches(text: str, keywords: list[str]) -> int:
    """텍스트 내 키워드 발견 개수 (중복 없이)."""
    count = 0
    for kw in keywords:
        if kw in text:
            count += 1
    return count


def compute_relevance(
    keyword: str,
    title: str | None,
    content_plain: str | None,
) -> tuple[int, bool]:
    """
    Returns:
        (score, is_relevant)
    """
    rule = COMPANY_RULES.get(keyword)
    if not rule:
        # 규칙 없는 키워드는 기본 통과
        return (MIN_RELEVANCE_SCORE, True)

    title_text = title or ""
    body_text = content_plain or ""
    full_text = title_text + " " + body_text

    score = 0

    # alias: 제목에서 발견 +15, 본문에서만 발견 +10
    for alias in rule.get("aliases", []):
        in_title = alias in title_text
        in_body = alias in body_text
        if in_title:
            score += 15
        elif in_body:
            score += 10

    # required_context: 제목+본문 통합
    for ctx in rule.get("required_context", []):
        if ctx in full_text:
            score += 3

    # exclude_keywords: 발견 시 강한 감점
    for excl in rule.get("exclude_keywords", []):
        if excl in full_text:
            score -= 20

    is_relevant = score >= MIN_RELEVANCE_SCORE
    return (score, is_relevant)


def filter_by_relevance(
    keyword: str,
    title: str | None,
    content_plain: str | None,
) -> bool:
    """
    기사가 해당 기업과 관련 있으면 True 반환.
    로그도 출력.
    """
    score, is_relevant = compute_relevance(keyword, title, content_plain)
    short_title = (title or "")[:40]
    if is_relevant:
        print(f"  [RELEVANT] [{keyword}] score={score} | {short_title}")
    else:
        print(f"  [SKIP-RELEVANCE] [{keyword}] score={score} | {short_title}")
    return is_relevant
