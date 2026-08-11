"""
The orchestrator: retrieve -> plan -> act -> evaluate -> learn -> persist.

This is a plain script, not a framework-managed agent -- per the
architecture doc's explicit rejection of Bedrock Agents, the loop's steps
are visible right here, in order, in one function you can read top to
bottom. This same function is what Day 6 wraps in a Lambda handler; the
handler will just call run_episode() with the query/project from the
event payload.

Run directly for local testing:
    python -m src.agent.orchestrator --project crynux --query "What is Crynux's current node architecture?"
"""
from __future__ import annotations

import argparse
import logging

from src.agent.config import Config, EpisodeResult, new_id
from src.agent.extractor import extract_claims
from src.agent.learner import compute_reliability_update, maybe_generate_lesson
from src.agent.memory import retrieve_memory
from src.agent.planner import plan_research
from src.agent.synthesizer import synthesize_answer
from src.db.connection import run_in_transaction
from src.db.repository import persist_episode
from src.sources.fetch import fetch_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agent_black_box")


def run_episode(config: Config, project: str, query: str, episode_id: str | None = None) -> EpisodeResult:
    episode_id = episode_id or new_id()
    log.info("episode=%s stage=retrieve project=%s query=%r", episode_id, project, query)

    # --- 1. RETRIEVE ---------------------------------------------------
    memory = retrieve_memory(config, project, query)
    log.info(
        "episode=%s stage=retrieve claims=%d lessons=%d sources=%d",
        episode_id, len(memory.relevant_claims), len(memory.relevant_lessons),
        len(memory.source_reliability),
    )

    # --- 2. PLAN ---------------------------------------------------------
    plan = plan_research(config, project, query, memory)
    log.info("episode=%s stage=plan strategy=%r planned_sources=%d",
              episode_id, plan.strategy_summary, len(plan.planned_sources))

    by_source_id = {s.source_id: s for s in memory.source_reliability}

    all_claims = []
    source_roles: dict[str, str] = {}
    reliability_updates = []
    lessons = []

    for planned in plan.planned_sources:
        source = by_source_id[planned.source_id]

        # --- 3. ACT (fetch) ---------------------------------------------
        fetch_result = fetch_source(planned.url)
        log.info("episode=%s stage=act source=%s success=%s",
                  episode_id, planned.domain, fetch_result.success)

        if not fetch_result.success:
            source_roles[source.source_id] = "rejected"
            reliability_updates.append(compute_reliability_update(source, was_successful=False))
            lesson = maybe_generate_lesson(
                config, source, f"Fetch failed: {fetch_result.error}", was_successful=False,
            )
            if lesson:
                lessons.append(lesson)
            continue

        # --- 4. EVALUATE (extract claims) --------------------------------
        claims = extract_claims(config, query, source.source_id, fetch_result.text)
        log.info("episode=%s stage=evaluate source=%s claims_extracted=%d",
                  episode_id, planned.domain, len(claims))

        was_successful = len(claims) > 0
        source_roles[source.source_id] = "used" if was_successful else "rejected"
        reliability_updates.append(compute_reliability_update(source, was_successful))

        if not was_successful:
            lesson = maybe_generate_lesson(
                config, source, "Fetch succeeded but no claims relevant to the query were found.",
                was_successful=False,
            )
            if lesson:
                lessons.append(lesson)

        all_claims.extend(claims)

    # --- 5. LEARN (synthesis is the last thing before persist) -----------
    final_answer = synthesize_answer(config, query, all_claims)
    log.info("episode=%s stage=learn lessons_generated=%d", episode_id, len(lessons))

    result = EpisodeResult(
        episode_id=episode_id,
        project=project,
        query=query,
        strategy_summary=plan.strategy_summary,
        claims=all_claims,
        lessons=lessons,
        final_answer=final_answer,
    )

    # --- 6. PERSIST --------------------------------------------------------
    # Everything above this line is recoverable if it fails -- nothing is
    # written yet. This is the one call where failure means the episode
    # did not happen, per the architecture doc's synchronous-persistence
    # rule: an episode is not "completed" until this commits.
    run_in_transaction(
        config, persist_episode, result,
        source_roles=source_roles, supersedes={}, reliability_updates=reliability_updates,
    )
    log.info("episode=%s stage=persist status=committed", episode_id)

    return result


def main():
    parser = argparse.ArgumentParser(description="Run one Agent Black Box research episode.")
    parser.add_argument("--project", required=True, help="e.g. crynux, neptune_cash, neptune_privacy")
    parser.add_argument("--query", required=True)
    args = parser.parse_args()

    config = Config.from_env()
    result = run_episode(config, args.project, args.query)

    print("\n--- FINAL ANSWER ---")
    print(result.final_answer)
    print(f"\nEpisode {result.episode_id}: {len(result.claims)} claims, {len(result.lessons)} lessons recorded.")


if __name__ == "__main__":
    main()
