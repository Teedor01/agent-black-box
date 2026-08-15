from __future__ import annotations

from src.agent.bedrock_client import generate_text
from src.agent.config import Config, ExtractedClaim

SYNTHESIS_SYSTEM_PROMPT = """You write a short, direct answer to a \
research query using only the claims provided. Cite nothing beyond what's \
given... do not add outside knowledge. If claims are sparse or partial, \
say so plainly rather than padding the answer. Plain text, no JSON, no \
markdown headers... 2-4 sentences."""


def synthesize_answer(config: Config, query: str, claims: list[ExtractedClaim]) -> str:
    if not claims:
        return "No claims were extracted from the planned sources this episode."

    claims_text = "\n".join(f"- {c.text} (confidence={c.confidence:.2f})" for c in claims)
    user_prompt = f"Research query: {query}\n\nClaims:\n{claims_text}\n\nAnswer:"
    return generate_text(config, SYNTHESIS_SYSTEM_PROMPT, user_prompt, max_tokens=512)
