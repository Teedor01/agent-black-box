from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests
import trafilatura


@dataclass
class FetchResult:
    url: str
    success: bool
    text: Optional[str] = None
    error: Optional[str] = None


def fetch_source(url: str, timeout_seconds: int = 15) -> FetchResult:
    try:
        response = requests.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": "AgentBlackBox/0.1 (research demo; hackathon submission)"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return FetchResult(url=url, success=False, error=str(exc))

    extracted = trafilatura.extract(response.text)
    if not extracted or not extracted.strip():
        return FetchResult(url=url, success=False, error="No extractable content (empty or non-article page)")

    return FetchResult(url=url, success=True, text=extracted)


def fetch_all(urls: list[str]) -> dict[str, FetchResult]:
   
    return {url: fetch_source(url) for url in urls}
