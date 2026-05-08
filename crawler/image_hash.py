from __future__ import annotations

from io import BytesIO

import httpx
import imagehash
from PIL import Image

from config import Settings


def compute_image_hashes(image_urls: list[str], settings: Settings) -> list[str]:
    hashes: list[str] = []
    seen: set[str] = set()
    headers = {"User-Agent": settings.user_agent}

    with httpx.Client(timeout=settings.request_timeout, follow_redirects=True, headers=headers) as client:
        for url in image_urls:
            try:
                response = client.get(url)
                response.raise_for_status()
                digest = phash_bytes(response.content)
            except Exception:
                continue

            if digest and digest not in seen:
                seen.add(digest)
                hashes.append(digest)

    return hashes


def phash_bytes(data: bytes) -> str | None:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return str(imagehash.phash(image.convert("RGB")))
