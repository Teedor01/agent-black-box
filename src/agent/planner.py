"""
Stage 2: plan.

This is the stage the entire project exists to demonstrate: retrieved
memory has to causally change what happens next, not just get displayed.
The prompt below explicitly hands the LLM source reliability history and
past lessons, and instructs it to factor them into source prioritization
-- not just "here's some context, do what you want."
"""
from __future__ import annotations

import json

from src.agent.bedrock_client import generate_text
from src.agent.config import Config, PlannedSource, ResearchPlan, RetrievedMemory, SourceRecord

PLANNER_SYSTEM_PROMPT = """You are the planning stage of a research agent. \
You will be given a research query, a project's known sources with their \
reliability history, and any lessons learned from past research on this \
project. Produce a research plan.

Rules:
- If a source has a low reliability_score or an associated lesson warning \
about it, deprioritize it -- do not simply list sources in the order given.
- If a lesson says a source produced outdated or incomplete information on \
a specific topic, note that in your rationale for that source and prefer \
sources with higher reliability or more recent claims for the same topic.
- Output ONLY valid JSON, no preamble, matching this exact shape:
{"strategy_summary": "...", "planned_sources": [{"source_id": "...", "priority": 1, "rationale": "..."}]}
- priority 1 is highest. Every source_id you use MUST come from the \
provided source list -- do not invent one.
"""


def _format_memory_for_prompt(memory: RetrievedMemory) -> str:
    lines = []

    lines.append("Known sources for this project:")
    if not memory.source_reliability:
        lines.append("  (none yet -- this is this project's first research episode)")
    for s in memory.source_reliability:
        lines.append(
            f"  - source_id={s.source_id} domain={s.domain} url={s.url} "
            f"reliability_score={s.reliability_score:.2f} times_used={s.times_used} "
            f"successful_uses={s.successful_uses} problematic_uses={s.problematic_uses}"
        )

    lines.append("\nRelevant lessons from past research on this project:")
    if not memory.relevant_lessons:
        lines.append("  (none yet)")
    for lesson in memory.relevant_lessons:
        lines.append(f"  - {lesson['text']} (confidence={lesson['confidence']:.2f})")

    lines.append("\nRelevant claims already established for this project:")
    if not memory.relevant_claims:
        lines.append("  (none yet)")
    for claim in memory.relevant_claims:
        lines.append(f"  - {claim['text']} (confidence={claim['confidence']:.2f})")

    return "\n".join(lines)


def plan_research(config: Config, project: str, query: str, memory: RetrievedMemory) -> ResearchPlan:
    user_prompt = (
        f"Research query: {query}\n"
        f"Project: {project}\n\n"
        f"{_format_memory_for_prompt(memory)}\n\n"
        f"Produce the research plan as JSON."
    )

    raw = generate_text(config, PLANNER_SYSTEM_PROMPT, user_prompt, max_tokens=1024)
    parsed = json.loads(raw)

    by_id: dict[str, SourceRecord] = {s.source_id: s for s in memory.source_reliability}
    planned_sources = []
    for entry in parsed["planned_sources"]:
        source = by_id.get(entry["source_id"])
        if source is None:
            continue  # ignore any hallucinated source_id rather than crash the plan
        planned_sources.append(
            PlannedSource(
                source_id=source.source_id,
                url=source.url,
                domain=source.domain,
                priority=entry["priority"],
                rationale=entry["rationale"],
            )
        )
    planned_sources.sort(key=lambda p: p.priority)

    return ResearchPlan(strategy_summary=parsed["strategy_summary"], planned_sources=planned_sources)
