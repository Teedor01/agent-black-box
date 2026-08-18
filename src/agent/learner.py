from __future__ import annotations

from typing import Optional

from src.agent.bedrock_client import embed_text, generate_text, parse_json_response
from src.agent.config import Config, Lesson, SourceRecord

LEARNING_RATE = 0.15

LESSON_SYSTEM_PROMPT = """You write a single short lesson (1-2 sentences) \
a research agent should remember about a source, given what happened when \
it was used this episode. Be specific and actionable -- state what future \
research should do differently, not just what happened.

Output ONLY valid JSON: {"text": "..."}
"""


def compute_reliability_update(source: SourceRecord, was_successful: bool) -> dict:
    outcome = 1.0 if was_successful else 0.0
    new_score = source.reliability_score * (1 - LEARNING_RATE) + outcome * LEARNING_RATE
    new_score = max(0.0, min(1.0, new_score))
    return {
        "source_id": source.source_id,
        "new_score": new_score,
        "times_used_delta": 1,
        "successful_delta": 1 if was_successful else 0,
        "problematic_delta": 0 if was_successful else 1,
    }


def maybe_generate_lesson(config: Config, source: SourceRecord, outcome_description: str,
                           was_successful: bool) -> Optional[Lesson]:
    
    if was_successful:
        return None

    user_prompt = (
        f"Source: {source.domain} ({source.url})\n"
        f"What happened this episode: {outcome_description}\n\n"
        f"Write the lesson as JSON."
    )
    raw = generate_text(config, LESSON_SYSTEM_PROMPT, user_prompt, max_tokens=256)
    parsed = parse_json_response(raw, context=f"maybe_generate_lesson(source_id={source.source_id})")
    text = parsed["text"]
    embedding = embed_text(config, text)

    return Lesson(text=text, confidence=0.7, embedding=embedding, source_id=source.source_id)


def generate_contradiction_lesson(config: Config, old_source: SourceRecord, contradiction) -> Lesson:
    
    user_prompt = (
        f"Source: {old_source.domain} ({old_source.url})\n"
        f'This source previously supported the claim: "{contradiction.existing_claim_text}"\n'
        f'New research found: "{contradiction.new_claim.text}"\n'
        f"Why they conflict: {contradiction.note}\n\n"
        f"Write the lesson as JSON."
    )
    raw = generate_text(config, LESSON_SYSTEM_PROMPT, user_prompt, max_tokens=256)
    parsed = parse_json_response(raw, context=f"generate_contradiction_lesson(source_id={old_source.source_id})")
    text = parsed["text"]
    embedding = embed_text(config, text)

    return Lesson(text=text, confidence=0.8, embedding=embedding, source_id=old_source.source_id)
