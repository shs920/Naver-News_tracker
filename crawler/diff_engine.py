"""
변경 감지 엔진.
title/body similarity 비교 + image pHash 비교.
"""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Any

EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
COMPARE_NOISE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"본문\s*글씨",
        r"SNS\s*기사보내기",
        r"이메일\(으\)로\s*기사보내기",
        r"다른\s*공유\s*찾기",
        r"기사스크랩",
        r"다른기사\s*보기",
        r"저작권자|무단전재|재배포\s*금지",
        r"개의\s*댓글|댓글\s*정렬|BEST댓글|댓글삭제|댓글수정",
        r"비밀번호|회원로그인|내\s*댓글\s*모음",
        r"많이\s*본\s*뉴스|최신기사|인기뉴스|관련기사",
        r"주소\s*:|대표전화\s*:|등록번호\s*:|발행인\s*:|편집인\s*:",
        r"All\s+rights\s+reserved",
    ]
]


def stable_hash(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def strip_email_addresses(value: str | None) -> str:
    if not value:
        return ""
    return EMAIL_PATTERN.sub("", value)


def normalize_meaningful_text(value: str | None) -> str:
    """비교용 텍스트 정규화: 소문자, 공백/기호 제거."""
    if not value:
        return ""
    value = strip_email_addresses(value)
    value = value.lower()
    value = re.sub(r'[\s\"\'""\u2018\u2019.,!?;:()\[\]{}<>\u00b7\u318d\u2026]+', "", value)
    return value.strip()


def strip_compare_noise(value: str | None) -> str:
    if not value:
        return ""
    kept: list[str] = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(pattern.search(line) for pattern in COMPARE_NOISE_PATTERNS):
            continue
        kept.append(line)
    return "\n".join(kept)


def change_ratio(before: str | None, after: str | None) -> float:
    before_norm = normalize_meaningful_text(before)
    after_norm  = normalize_meaningful_text(after)
    if not before_norm and not after_norm:
        return 0.0
    return 1.0 - SequenceMatcher(None, before_norm, after_norm).ratio()


def body_change_ratio(before: str | None, after: str | None) -> float:
    before_clean = strip_compare_noise(before)
    after_clean = strip_compare_noise(after)
    before_full = normalize_meaningful_text(before_clean)
    after_full = normalize_meaningful_text(after_clean)
    if not before_full and not after_full:
        return 0.0
    if before_full == after_full:
        return 0.0
    if before_full and after_full and (before_full in after_full or after_full in before_full):
        shorter = min(len(before_full), len(after_full))
        longer = max(len(before_full), len(after_full))
        added_ratio = 1.0 - (shorter / max(longer, 1))
        if added_ratio <= 0.03:
            return 0.0

    whole_ratio = 1.0 - SequenceMatcher(None, before_full, after_full).ratio()
    if whole_ratio <= 0.015:
        return 0.0

    before_paras = split_normalized_paragraphs(before_clean)
    after_paras = split_normalized_paragraphs(after_clean)
    if not before_paras and not after_paras:
        return 0.0
    if not before_paras or not after_paras:
        return 1.0

    pairs: list[tuple[float, int, int]] = []
    for before_index, before_para in enumerate(before_paras):
        for after_index, after_para in enumerate(after_paras):
            ratio = SequenceMatcher(None, before_para, after_para).ratio()
            if ratio >= 0.78:
                pairs.append((ratio, before_index, after_index))

    pairs.sort(reverse=True)
    used_before: set[int] = set()
    used_after: set[int] = set()
    changed_chars = 0.0

    for ratio, before_index, after_index in pairs:
        if before_index in used_before or after_index in used_after:
            continue
        used_before.add(before_index)
        used_after.add(after_index)
        changed_chars += (1.0 - ratio) * max(
            len(before_paras[before_index]),
            len(after_paras[after_index]),
        )

    changed_chars += sum(
        len(paragraph)
        for index, paragraph in enumerate(before_paras)
        if index not in used_before
    )
    changed_chars += sum(
        len(paragraph)
        for index, paragraph in enumerate(after_paras)
        if index not in used_after
    )
    total_chars = max(sum(map(len, before_paras)), sum(map(len, after_paras)), 1)
    return min(1.0, changed_chars / total_chars)


def split_normalized_paragraphs(value: str | None) -> list[str]:
    if not value:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n{1,}", value) if p.strip()]
    normalized = [normalize_meaningful_text(p) for p in paragraphs]
    return [p for p in normalized if len(p) >= 12]


def image_change_ratio(
    before_hashes: list[str],
    after_hashes: list[str],
    threshold: int,
) -> float:
    if not before_hashes and not after_hashes:
        return 0.0
    if not before_hashes or not after_hashes:
        return 1.0

    matched = 0
    used_after: set[int] = set()
    for before_hash in before_hashes:
        for idx, after_hash in enumerate(after_hashes):
            if idx in used_after:
                continue
            if hamming_distance(before_hash, after_hash) <= threshold:
                matched += 1
                used_after.add(idx)
                break

    denominator = max(len(before_hashes), len(after_hashes))
    return 1.0 - (matched / denominator)


def hamming_distance(left: str, right: str) -> int:
    try:
        return bin(int(left, 16) ^ int(right, 16)).count("1")
    except ValueError:
        return 64


def detect_change(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    title_threshold: float,
    body_threshold: float,
    image_threshold: float,
    image_hamming_threshold: int,
) -> dict[str, Any]:
    title_ratio = change_ratio(previous.get("title"), current.get("title"))
    body_ratio  = body_change_ratio(previous.get("content_plain"), current.get("content_plain"))
    image_ratio = image_change_ratio(
        previous.get("image_hashes") or [],
        current.get("image_hashes") or [],
        image_hamming_threshold,
    )
    previous_image_urls = previous.get("image_urls") or []
    current_image_urls = current.get("image_urls") or []

    title_changed   = title_ratio  >= title_threshold
    body_changed    = body_ratio   >= body_threshold
    image_changed   = image_ratio  >= image_threshold
    # Image-only changes are too noisy for news pages because recommendation
    # blocks and lazy-loaded thumbnails move frequently across publishers.
    if image_changed and not title_changed and not body_changed:
        image_changed = False
        image_ratio = 0.0
    deleted_changed = bool(previous.get("is_deleted", False)) != bool(current.get("is_deleted", False))

    score = max(title_ratio, body_ratio, image_ratio, 1.0 if deleted_changed else 0.0)

    return {
        "title_changed":    title_changed,
        "body_changed":     body_changed,
        "image_changed":    image_changed,
        "deleted_changed":  deleted_changed,
        "change_score":     round(score, 5),
        "title_change_ratio": round(title_ratio, 5),
        "body_change_ratio":  round(body_ratio, 5),
        "image_change_ratio": round(image_ratio, 5),
        "has_meaningful_change": title_changed or body_changed or image_changed or deleted_changed,
    }
