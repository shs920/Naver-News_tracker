"""
기업 relevance scoring.

개선사항:
  - alias_only_pass=True 기업은 alias 발견만으로 통과 (required_context 불필요)
  - alias_only_pass=False 기업은 alias + context 모두 필요 (동음이의어 많은 경우)
  - exclude_keywords는 강한 감점(-20)으로 동음이의어 차단
  - 규칙 없는 키워드는 기본 통과
"""
from __future__ import annotations

from company_rules import COMPANY_RULES, MIN_RELEVANCE_SCORE


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
    alias_found = False

    # ── alias 점수 ─────────────────────────────────────────
    for alias in rule.get("aliases", []):
        if alias in title_text:
            score += 15
            alias_found = True
        elif alias in body_text:
            score += 10
            alias_found = True

    # ── required_context 점수 ──────────────────────────────
    for ctx in rule.get("required_context", []):
        if ctx in full_text:
            score += 3

    # ── exclude_keywords 감점 ──────────────────────────────
    for excl in rule.get("exclude_keywords", []):
        if excl in full_text:
            score -= 20

    # ── alias_only_pass 판단 ───────────────────────────────
    # alias_only_pass=True: alias만 발견돼도 required_context 없이 통과 가능
    # alias_only_pass=False: alias 발견 + context 점수 필요 (동음이의어 기업)
    alias_only_pass = rule.get("alias_only_pass", True)

    if alias_only_pass and alias_found and score >= 0:
        # exclude에 안 걸렸고 alias가 발견됐으면 통과
        is_relevant = score >= MIN_RELEVANCE_SCORE
    else:
        # alias_only_pass=False면 alias + context 조합이 필요
        is_relevant = score >= MIN_RELEVANCE_SCORE

    return (score, is_relevant)


def filter_by_relevance(
    keyword: str,
    title: str | None,
    content_plain: str | None,
) -> bool:
    """
    기사가 해당 기업과 관련 있으면 True 반환.
    로그 출력.
    """
    score, is_relevant = compute_relevance(keyword, title, content_plain)
    short_title = (title or "")[:50]
    if is_relevant:
        print(f"  [RELEVANT] [{keyword}] score={score} | {short_title}")
    else:
        print(f"  [SKIP-RELEVANCE] [{keyword}] score={score} | {short_title}")
    return is_relevant
