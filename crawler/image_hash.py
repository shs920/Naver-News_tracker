"""
이미지 pHash 계산 모듈.
imagehash 라이브러리 사용 (16진수 문자열 반환).
"""
from __future__ import annotations

from io import BytesIO

import httpx
import imagehash
from PIL import Image

from config import Settings


def compute_image_hashes(image_urls: list[str], settings: Settings) -> list[str]:
    _, hashes = compute_image_fingerprints(image_urls, settings)
    return hashes


def compute_image_fingerprints(image_urls: list[str], settings: Settings) -> tuple[list[str], list[str]]:
    """Return image URLs and pHashes with matching indexes.

    Failed downloads and duplicate image hashes are removed from both arrays so
    web-side image comparison never pairs a URL with another image's hash.
    """
    kept_urls: list[str] = []
    hashes: list[str] = []
    seen: set[str] = set()
    headers = {"User-Agent": settings.user_agent}

    with httpx.Client(
        timeout=settings.request_timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        for url in image_urls:
            try:
                response = client.get(url)
                response.raise_for_status()
                digest = _phash_bytes(response.content)
            except Exception:
                continue

            if digest and digest not in seen:
                seen.add(digest)
                kept_urls.append(url)
                hashes.append(digest)

    return kept_urls, hashes


def _phash_bytes(data: bytes) -> str | None:
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return str(imagehash.phash(image.convert("RGB")))
    except Exception:
        return None
