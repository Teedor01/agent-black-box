# Agent Black Box

A research agent that remembers which sources and research strategies
worked — and which didn't — and changes how it researches next time
because of it.

Built for the [CockroachDB × AWS Hackathon: Build with Agentic Memory](https://cockroachdb-ai.devpost.com/)
(submission window closes August 18, 2026).

## What this is

Most research agents start from zero every session. Agent Black Box
doesn't: every research task is recorded as a structured "episode" in
CockroachDB — which sources it used, what it concluded, what turned out to
be wrong. Before starting a new task, it retrieves that history and lets it
change what it does — which sources it trusts, how much verification it
demands.

The thing being demonstrated technically: retrieval isn't cosmetic. It has
a measurable, causal effect on the agent's next decision.

Full architecture, data flows, schema rationale, and judging-criteria
mapping: see [`architecture/agent-black-box-architecture.md`](architecture/agent-black-box-architecture.md).

## CockroachDB tools used

- **Distributed Vector Indexing** — semantic retrieval over past claims and
  lessons, partitioned per-project via a prefix column so retrieval stays
  fast as the memory store grows.
- **Managed MCP Server** — used two ways: dev-time for schema/query work,
  and at runtime as the agent's own read-only memory-retrieval dependency
  during its planning step.
- **ccloud CLI** — cluster provisioning only (disclosed as tooling, not
  claimed as a core integration).

## AWS services used

- **AWS Lambda** — runs the agent's decision loop (stateless; all state
  lives in CockroachDB).
- **Amazon Bedrock** — LLM calls for planning, claim extraction, lesson
  generation, and embeddings.

## Status

Days 1-7 of the 10-day plan are done:
- Infrastructure setup plan and schema (Day 1)
- Real demo source corpus, Crynux drift pair and Neptune fork relationship
  both verified (Day 2)
- Core agent loop as a script — retrieve → plan → act → evaluate → learn →
  persist (Days 3-4)
- Contradiction detection — a superseded claim dings the old source and
  generates a lesson a later episode's plan() reads and acts on (Day 5)
- Lambda handler wrapping the loop, Windows-safe packaging script,
  deployment instructions (Day 6)
- MCP retrieve-path gap closed — the agent's own reads go through the
  Managed MCP Server's read-only credential, not psycopg
- Web UI (Day 7): Next.js app with an Ask view (submit a query, see the
  strategy/answer/claims/lessons) and a Memory Trace view (source
  reliability, recent episodes, lessons, and contradictions — the view
  that actually shows the "agent remembers and corrects itself" claim)

All 14 dry-run tests passing. The Next.js build was run and verified in
this environment — both pages compile cleanly.

**One thing left before trusting the retrieve path in the real demo**:
the MCP client's exact tool name and result-parsing assumptions are
unconfirmed against your live server — run
`python scripts\verify_mcp_connection.py` once with your real bearer
token (see `infra/DEPLOY.md`).

## Running the agent loop

Requires real credentials — see [`infra/SETUP.md`](infra/SETUP.md) for
provisioning. Copy `.env.example` to `.env` and fill in real values first.

```
pip install -r requirements.txt --break-system-packages
python -m src.agent.orchestrator --project crynux --query "What is Crynux's current node architecture?"
```

### Deploying to Lambda and running the web UI

See [`infra/DEPLOY.md`](infra/DEPLOY.md).

### Running the dry-run tests (no real credentials needed)

Every Bedrock/CockroachDB/network call is mocked at the module boundary —
this validates control flow and data wiring, not the external services:

```
python -m pytest tests/ -v
```




## License

MIT — see [`LICENSE`](LICENSE).

## Prior work disclosure

The drift-detection *pattern* (trusted baseline → current state → drift →
incident) used conceptually for source-reliability tracking here was
inspired by an earlier, separate project of the author's ("Silent ML Drift
Sentinel," built for a different hackathon). No code from that project is
reused — this is a new implementation, built during this hackathon's
submission period.
