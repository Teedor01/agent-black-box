"""
Lightweight contradiction detection (architecture doc Section 5). Runs
during evaluate, after claims are extracted, before persist. Vector
search for the closest existing claim, then one LLM judgment call only
for pairs already close enough to plausibly be about the same fact --
not a full fact-verification pass over every claim pair.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from src.agent.bedrock_client import generate_text
from src.agent.config import Config, ExtractedClaim
from src.db.connection import get_connection
from src.db.repository import find_closest_claim

# L2 distance cutoff -- only ask the LLM to judge a pair if the new claim
# is already this close to something we've claimed before. Tune this
# empirically against your embedding model; it's a recall/precision
# knob, not a correctness threshold.
CANDIDATE_DISTANCE_THRESHOLD = 0.6

CONTRADICTION_SYSTEM_PROMPT = """You compare two factual claims about the \
same project and decide whether the new claim contradicts or supersedes \
the existing one -- meaning someone who believed only the existing claim \
would now be misled or working from an incomplete picture.

Claims that simply add unrelated detail are NOT a conflict. A claim that \
narrows, broadens, corrects, or supersedes the scope of an earlier claim \
IS a conflict, even if the earlier claim wasn't strictly false -- e.g. \
"nodes only do X" superseded by "nodes now do X and Y" counts, because \
the earlier claim would mislead someone about current scope.

Output ONLY valid JSON: {"conflict": true/false, "note": "one sentence explaining why"}
"""


@dataclass
class ContradictionResult:
    new_claim: ExtractedClaim
    existing_claim_id: str
    existing_claim_text: str
    existing_source_id: Optional[str]
    note: str


def detect_contradictions(config: Config, project: str, new_claims: list[ExtractedClaim]) -> list[ContradictionResult]:
    results = []
    with get_connection(config) as conn:
        with conn.cursor() as cur:
            for claim in new_claims:
                candidate = find_closest_claim(cur, project, claim.embedding)
                if candidate is None or candidate["distance"] > CANDIDATE_DISTANCE_THRESHOLD:
                    continue

                user_prompt = (
                    f"Existing claim: {candidate['text']}\n"
                    f"New claim: {claim.text}\n\n"
                    f"Judge as JSON."
                )
                raw = generate_text(config, CONTRADICTION_SYSTEM_PROMPT, user_prompt, max_tokens=256)
                judged = json.loads(raw)

                if judged.get("conflict"):
                    results.append(ContradictionResult(
                        new_claim=claim,
                        existing_claim_id=candidate["claim_id"],
                        existing_claim_text=candidate["text"],
                        existing_source_id=candidate["source_id"],
                        note=judged.get("note", ""),
                    ))
    return results
