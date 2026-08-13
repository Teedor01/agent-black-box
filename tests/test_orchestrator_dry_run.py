"""
Dry-run test: proves retrieve -> plan -> act -> evaluate -> learn ->
persist executes in order and wires data correctly between stages,
without touching real AWS or CockroachDB. Every Bedrock/DB/network call
is mocked at the module boundary -- this validates the orchestrator's
logic, not the external services.

Run: python -m pytest tests/test_orchestrator_dry_run.py -v
"""
from __future__ import annotations

import json
from unittest.mock import patch

from src.agent.config import Config, SourceRecord
from src.sources.fetch import FetchResult


def fake_config() -> Config:
    return Config(
        cockroachdb_connection_string="postgresql://fake",
        aws_region="us-east-1",
        bedrock_embedding_model_id="amazon.titan-embed-text-v2:0",
        bedrock_text_model_id="anthropic.claude-sonnet-5",
        mcp_endpoint="https://cockroachlabs.cloud/mcp",
        mcp_bearer_token="fake-token",
    )


FAKE_SOURCE = SourceRecord(
    source_id="11111111-1111-1111-1111-111111111111",
    url="https://docs.crynux.io/",
    domain="docs.crynux.io",
    source_type="official_docs",
    project="crynux",
    reliability_score=0.5,
    times_used=0,
    successful_uses=0,
    problematic_uses=0,
)


def test_full_loop_runs_in_order_and_persists():
    from src.agent import orchestrator

    plan_json = json.dumps({
        "strategy_summary": "Consult docs.crynux.io for current node architecture.",
        "planned_sources": [
            {"source_id": FAKE_SOURCE.source_id, "priority": 1, "rationale": "Official current docs, no known issues."}
        ],
    })
    claims_json = json.dumps({
        "claims": [
            {"text": "Crynux nodes execute LLM/VLM inference and fine-tuning tasks.", "confidence": 0.9}
        ]
    })

    # generate_text is called 3 times in sequence: planner, extractor, synthesizer
    generate_text_responses = iter([plan_json, claims_json, "Crynux nodes now support LLM/VLM inference, not just image generation."])

    call_log = []

    def fake_generate_text(config, system_prompt, user_prompt, max_tokens=1024):
        call_log.append(system_prompt[:30])
        return next(generate_text_responses)

    def fake_embed_text(config, text):
        return [0.1, 0.2, 0.3]

    def fake_fetch_source(url, timeout_seconds=15):
        return FetchResult(url=url, success=True, text="Crynux Network supports LLM/VLM inference and fine-tuning.")

    persist_calls = []

    def fake_run_in_transaction(config, fn, *args, max_retries=3, **kwargs):
        # Capture what persist_episode would have received, without a real cursor/DB.
        persist_calls.append({"args": args, "kwargs": kwargs})
        return None

    def fake_retrieve_memory(config, project, query):
        from src.agent.config import RetrievedMemory
        return RetrievedMemory(relevant_claims=[], relevant_lessons=[], source_reliability=[FAKE_SOURCE])

    with patch("src.agent.planner.generate_text", fake_generate_text), \
         patch("src.agent.extractor.generate_text", fake_generate_text), \
         patch("src.agent.synthesizer.generate_text", fake_generate_text), \
         patch("src.agent.extractor.embed_text", fake_embed_text), \
         patch("src.agent.orchestrator.retrieve_memory", fake_retrieve_memory), \
         patch("src.agent.orchestrator.fetch_source", fake_fetch_source), \
         patch("src.agent.orchestrator.detect_contradictions", lambda *a, **k: []), \
         patch("src.agent.orchestrator.run_in_transaction", fake_run_in_transaction):

        config = fake_config()
        result = orchestrator.run_episode(config, project="crynux", query="What is Crynux's current node architecture?")

    # --- assertions about what happened, in order ---
    assert len(call_log) == 3, "planner, extractor, and synthesizer should each call generate_text exactly once"

    assert result.status == "completed"
    assert len(result.claims) == 1
    assert result.claims[0].text.startswith("Crynux nodes execute LLM/VLM")
    assert result.claims[0].source_id == FAKE_SOURCE.source_id
    assert "LLM/VLM" in result.final_answer

    assert len(persist_calls) == 1, "persist should be called exactly once, after everything else"
    persisted_result = persist_calls[0]["args"][0]
    assert persisted_result.episode_id == result.episode_id
    reliability_updates = persist_calls[0]["kwargs"]["reliability_updates"]
    assert reliability_updates[0]["source_id"] == FAKE_SOURCE.source_id
    assert reliability_updates[0]["successful_delta"] == 1, "a source that yielded a claim should be scored as successful"

    print("OK: retrieve -> plan -> act -> evaluate -> learn -> persist all ran in order with correct data flow")


def test_fetch_failure_does_not_crash_episode_and_scores_source_down():
    from src.agent import orchestrator

    plan_json = json.dumps({
        "strategy_summary": "Try the known source.",
        "planned_sources": [
            {"source_id": FAKE_SOURCE.source_id, "priority": 1, "rationale": "Only source we know about."}
        ],
    })

    def fake_generate_text(config, system_prompt, user_prompt, max_tokens=1024):
        if "plan" in system_prompt.lower() or "planning" in system_prompt.lower():
            return plan_json
        if "lesson" in system_prompt.lower():
            return json.dumps({"text": "This source failed to fetch during research; consider an alternate source next time."})
        return "No claims were extracted from the planned sources this episode."

    def fake_embed_text(config, text):
        return [0.0, 0.0, 0.0]

    def fake_fetch_source(url, timeout_seconds=15):
        return FetchResult(url=url, success=False, error="Connection timed out")

    persist_calls = []

    def fake_run_in_transaction(config, fn, *args, max_retries=3, **kwargs):
        persist_calls.append({"args": args, "kwargs": kwargs})
        return None

    def fake_retrieve_memory(config, project, query):
        from src.agent.config import RetrievedMemory
        return RetrievedMemory(relevant_claims=[], relevant_lessons=[], source_reliability=[FAKE_SOURCE])

    with patch("src.agent.planner.generate_text", fake_generate_text), \
         patch("src.agent.extractor.generate_text", fake_generate_text), \
         patch("src.agent.synthesizer.generate_text", fake_generate_text), \
         patch("src.agent.learner.generate_text", fake_generate_text), \
         patch("src.agent.extractor.embed_text", fake_embed_text), \
         patch("src.agent.learner.embed_text", fake_embed_text), \
         patch("src.agent.orchestrator.retrieve_memory", fake_retrieve_memory), \
         patch("src.agent.orchestrator.fetch_source", fake_fetch_source), \
         patch("src.agent.orchestrator.detect_contradictions", lambda *a, **k: []), \
         patch("src.agent.orchestrator.run_in_transaction", fake_run_in_transaction):

        config = fake_config()
        result = orchestrator.run_episode(config, project="crynux", query="What is Crynux's current node architecture?")

    assert result.status == "completed", "a fetch failure should not crash the episode"
    assert len(result.claims) == 0
    assert len(result.lessons) == 1, "a fetch failure should generate exactly one lesson"

    reliability_updates = persist_calls[0]["kwargs"]["reliability_updates"]
    assert reliability_updates[0]["problematic_delta"] == 1
    assert reliability_updates[0]["new_score"] < FAKE_SOURCE.reliability_score, "score should move down after a failure"

    print("OK: fetch failure handled gracefully, source scored down, lesson recorded, episode still completes")


def test_contradiction_supersedes_old_claim_and_dings_old_source():
    """The money shot, tested at the unit level: a new claim that
    contradicts a prior one produces a lesson about the OLD source,
    dings that source's reliability, and records the supersession --
    all in the same episode's persist call. This is what makes a LATER
    episode's plan() stage deprioritize the old source."""
    from src.agent.contradiction import ContradictionResult
    from src.agent.config import ExtractedClaim
    from src.agent import orchestrator

    OLD_SOURCE = SourceRecord(
        source_id="22222222-2222-2222-2222-222222222222",
        url="https://docs.crynux.io/system-design/network-architecture",
        domain="docs.crynux.io", source_type="official_docs", project="crynux",
        reliability_score=0.5, times_used=1, successful_uses=1, problematic_uses=0,
    )
    NEW_SOURCE = SourceRecord(
        source_id="33333333-3333-3333-3333-333333333333",
        url="https://docs.crynux.io/", domain="docs.crynux.io", source_type="official_docs",
        project="crynux", reliability_score=0.5, times_used=0, successful_uses=0, problematic_uses=0,
    )

    plan_json = json.dumps({
        "strategy_summary": "Consult current docs.",
        "planned_sources": [{"source_id": NEW_SOURCE.source_id, "priority": 1, "rationale": "Most recent."}],
    })
    claims_json = json.dumps({
        "claims": [{"text": "Crynux nodes now support LLM/VLM inference and fine-tuning, not just image generation.", "confidence": 0.9}]
    })

    def fake_generate_text(config, system_prompt, user_prompt, max_tokens=1024):
        if "planning stage" in system_prompt.lower():
            return plan_json
        if "compare two factual claims" in system_prompt.lower():
            return json.dumps({"conflict": True, "note": "New claim broadens scope beyond the old claim's image-generation-only framing."})
        if "lesson" in system_prompt.lower():
            return json.dumps({"text": "docs.crynux.io/system-design/network-architecture understated node scope; verify architecture claims against the current docs homepage."})
        if "extract" in system_prompt.lower() or "claims" in system_prompt.lower():
            return claims_json
        return "Crynux nodes now support LLM/VLM inference and fine-tuning."

    def fake_embed_text(config, text):
        return [0.1, 0.1, 0.1]

    def fake_fetch_source(url, timeout_seconds=15):
        return FetchResult(url=url, success=True, text="Crynux nodes now support LLM/VLM inference and fine-tuning.")

    def fake_retrieve_memory(config, project, query):
        from src.agent.config import RetrievedMemory
        # Both sources are already known -- this is Session 2, not the project's first episode.
        return RetrievedMemory(relevant_claims=[], relevant_lessons=[],
                                source_reliability=[OLD_SOURCE, NEW_SOURCE])

    fake_contradiction = ContradictionResult(
        new_claim=ExtractedClaim(text=json.loads(claims_json)["claims"][0]["text"], confidence=0.9,
                                  embedding=[0.1, 0.1, 0.1], source_id=NEW_SOURCE.source_id),
        existing_claim_id="44444444-4444-4444-4444-444444444444",
        existing_claim_text="Crynux nodes execute Stable Diffusion image generation tasks.",
        existing_source_id=OLD_SOURCE.source_id,
        note="New claim broadens scope beyond the old claim's image-generation-only framing.",
    )

    persist_calls = []

    def fake_run_in_transaction(config, fn, *args, max_retries=3, **kwargs):
        persist_calls.append({"args": args, "kwargs": kwargs})
        return None

    with patch("src.agent.planner.generate_text", fake_generate_text), \
         patch("src.agent.extractor.generate_text", fake_generate_text), \
         patch("src.agent.synthesizer.generate_text", fake_generate_text), \
         patch("src.agent.learner.generate_text", fake_generate_text), \
         patch("src.agent.extractor.embed_text", fake_embed_text), \
         patch("src.agent.learner.embed_text", fake_embed_text), \
         patch("src.agent.orchestrator.retrieve_memory", fake_retrieve_memory), \
         patch("src.agent.orchestrator.fetch_source", fake_fetch_source), \
         patch("src.agent.orchestrator.detect_contradictions", lambda *a, **k: [fake_contradiction]), \
         patch("src.agent.orchestrator.run_in_transaction", fake_run_in_transaction):

        config = fake_config()
        result = orchestrator.run_episode(config, project="crynux", query="What is Crynux's current node architecture?")

    kwargs = persist_calls[0]["kwargs"]

    assert kwargs["supersedes"] == {fake_contradiction.new_claim.claim_id: fake_contradiction.existing_claim_id}
    assert kwargs["contradictions"][0]["conflicting_claim_id"] == fake_contradiction.existing_claim_id

    old_source_updates = [u for u in kwargs["reliability_updates"] if u["source_id"] == OLD_SOURCE.source_id]
    assert len(old_source_updates) == 1, "the OLD source (not the new one) should get dinged"
    assert old_source_updates[0]["problematic_delta"] == 1
    assert old_source_updates[0]["new_score"] < OLD_SOURCE.reliability_score

    lesson_sources = [l.source_id for l in result.lessons]
    assert OLD_SOURCE.source_id in lesson_sources, "a lesson should be recorded against the OLD source"

    print("OK: contradiction supersedes old claim, dings old source, records lesson -- ready for a later episode's plan() to act on")


if __name__ == "__main__":
    test_full_loop_runs_in_order_and_persists()
    test_fetch_failure_does_not_crash_episode_and_scores_source_down()
    test_contradiction_supersedes_old_claim_and_dings_old_source()
    print("\nAll dry-run checks passed.")
