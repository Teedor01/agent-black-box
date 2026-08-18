from __future__ import annotations

from src.agent.bedrock_client import embed_text, generate_text, parse_json_response
from src.agent.config import Config, ExtractedClaim

EXTRACTOR_SYSTEM_PROMPT = """You extract factual claims from source text \
for a research agent. Given a research query and source text, extract up \
to 5 distinct factual claims that are directly relevant to the query.

Rules:
- Each claim must be a single, self-contained factual statement in your \
own words, do not quote the source verbatim.
- confidence (0.0-1.0) reflects how clearly and directly the source text \
supports the claim, not how important the claim is.
- Output ONLY valid JSON, no preamble, matching this exact shape:
{"claims": [{"text": "...", "confidence": 0.9}]}
- If the text contains nothing relevant to the query, output {"claims": []}.
"""


def extract_claims(config: Config, query: str, source_id: str, source_text: str) -> list[ExtractedClaim]:
    # Trim aggressively -- this is claim extraction, not full-document
    # analysis, and keeping the prompt small keeps latency and cost down.
    trimmed = source_text[:6000]

    user_prompt = f"Research query: {query}\n\nSource text:\n{trimmed}\n\nExtract claims as JSON."
    raw = generate_text(config, EXTRACTOR_SYSTEM_PROMPT, user_prompt, max_tokens=1024)
    parsed = parse_json_response(raw, context=f"extract_claims(source_id={source_id})")

    claims = []
    for entry in parsed.get("claims", []):
        embedding = embed_text(config, entry["text"])
        claims.append(
            ExtractedClaim(
                text=entry["text"],
                confidence=float(entry["confidence"]),
                embedding=embedding,
                source_id=source_id,
            )
        )
    return claims
