"""
Fetches a URL and extracts readable text from it, matching the extraction
approach used in the Research Agent MVP (requests + trafilatura). Kept
separate from the planner/extractor so a source failure (network error,
paywall, empty page) is handled at one clear boundary -- see
handle_fetch_failure() below, which is what Section 10 of the
architecture doc calls "source fetch failures" as a named failure mode
the loop must survive without corrupting an episode.
"""
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
    """Fetches each URL independently -- one failure doesn't abort the
    others. The orchestrator decides what a partial-failure episode means
    (e.g. still completes with fewer claims, and the failed source itself
    becomes a data point for reliability scoring in a later episode)."""
    return {url: fetch_source(url) for url in urls}
