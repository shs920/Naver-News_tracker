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
    title_fold = title_text.casefold()
    body_fold = body_text.casefold()
    full_fold = full_text.casefold()

    score = 0
    alias_found = False

    # ── alias 점수 ─────────────────────────────────────────
    aliases = [str(alias) for alias in rule.get("aliases", [])]
    contexts = [str(ctx) for ctx in rule.get("required_context", [])]

    title_alias_found = False
    body_alias_found = False

    for alias in aliases:
        alias_fold = alias.casefold()
        if alias_fold in title_fold:
            score += 15
            alias_found = True
            title_alias_found = True
        elif alias_fold in body_fold:
            score += 10
            alias_found = True
            body_alias_found = True

    # ── required_context 점수 ──────────────────────────────
    for ctx in contexts:
        if ctx.casefold() in full_fold:
            score += 3

    # ── exclude_keywords 감점 ──────────────────────────────
    for excl in rule.get("exclude_keywords", []):
        if str(excl).casefold() in full_fold:
            score -= 20

    # ── alias_only_pass 판단 ───────────────────────────────
    # alias_only_pass=True: alias만 발견돼도 required_context 없이 통과 가능
    # alias_only_pass=False: alias 발견 + context 점수 필요 (동음이의어 기업)
    alias_only_pass = rule.get("alias_only_pass", True)

    body_only_alias = body_alias_found and not title_alias_found
    if body_only_alias and not _has_near_context(body_text, aliases, contexts):
        return (score, False)

    if alias_only_pass and alias_found and score >= 0:
        # exclude에 안 걸렸고 alias가 발견됐으면 통과
        is_relevant = score >= MIN_RELEVANCE_SCORE
    else:
        # alias_only_pass=False면 alias + context 조합이 필요
        is_relevant = score >= MIN_RELEVANCE_SCORE

    return (score, is_relevant)


def _has_near_context(text: str, aliases: list[str], contexts: list[str], window: int = 180) -> bool:
    if not text:
        return False
    text_fold = text.casefold()
    context_folds = [ctx.casefold() for ctx in contexts]
    for alias in aliases:
        alias_fold = alias.casefold()
        start = text_fold.find(alias_fold)
        while start >= 0:
            left = max(0, start - window)
            right = min(len(text_fold), start + len(alias_fold) + window)
            snippet = text_fold[left:right]
            if any(ctx in snippet for ctx in context_folds):
                return True
            start = text_fold.find(alias_fold, start + len(alias_fold))
    return False


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
