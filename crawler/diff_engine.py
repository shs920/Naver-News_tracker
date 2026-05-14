"""
변경 감지 엔진.
title/body similarity 비교 + image pHash 비교.
"""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Any


def stable_hash(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_meaningful_text(value: str | None) -> str:
    """비교용 텍스트 정규화: 소문자, 공백/기호 제거."""
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r'[\s\"\'""\u2018\u2019.,!?;:()\[\]{}<>\u00b7\u318d\u2026]+', "", value)
    return value.strip()


def change_ratio(before: str | None, after: str | None) -> float:
    before_norm = normalize_meaningful_text(before)
    after_norm  = normalize_meaningful_text(after)
    if not before_norm and not after_norm:
        return 0.0
    return 1.0 - SequenceMatcher(None, before_norm, after_norm).ratio()


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
    body_ratio  = change_ratio(previous.get("content_plain"), current.get("content_plain"))
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
    # Avoid noisy image-only alerts caused by a site's fallback og:image,
    # logo, or crawler-side image extraction differences.
    if image_changed and title_ratio == 0 and body_ratio == 0:
        if not previous_image_urls or not current_image_urls:
            image_changed = False
            image_ratio = 0.0
        elif len(previous_image_urls) == 1 and len(current_image_urls) == 1:
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
