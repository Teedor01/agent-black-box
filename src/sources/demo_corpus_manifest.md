# Demo Source Corpus — Manifest

Every source below is real and was
retrieved via web search/fetch on 2026-08-10... nothing here is fabricated,
per the architecture doc's explicit constraint. Dates noted are the search
index's observed/crawl dates for that page, not necessarily the page's own
"last updated" date — treat them as "content observed as of," not an
authoritative revision timestamp, unless the page states its own date.

## Crynux — the demo's core drift pair

This is the scenario the architecture doc used as its running example
("Research Crynux's node architecture") — and it turns out real Crynux
documentation actually contains a genuine version of it. No invented
scenario needed.

**Source 1 (the one that goes stale) — narrower/older framing**
- URL: https://docs.crynux.io/system-design/network-architecture
- Domain: docs.crynux.io
- Type: official_docs
- Observed: page content indexed 2025-07-16
- Claim it supports: Crynux nodes execute Stable Diffusion image generation
  tasks for applications, and are rewarded in tokens for correct output,
  verified via a blockchain consensus mechanism that prevents cheating.
- Framing risk: read on its own, this describes node work as
  Stable-Diffusion-only, which is no longer the full picture (see Source 2).

**Source 2 (the correction) — current framing**
- URL: https://docs.crynux.io/
- Domain: docs.crynux.io
- Type: official_docs
- Observed: page content indexed 2026-06-25
- Claim it supports: Crynux Network is now described as a decentralized AI
  compute network supporting LLM/VLM inference and fine-tuning tasks, not
  image generation alone, coordinated through a named consensus protocol
  (vssML) for detecting and penalizing malicious node behavior.
- Also relevant: the docs list three successive named network releases...
  Lithium, Helium, and Hydrogen — confirming the protocol has gone through
  multiple real architectural generations, which supports the "node scope
  expanded over time" narrative rather than treating it as a one-off error.

**Demo mechanics implied by this pair:**
- Session 1: agent researches "Crynux node architecture," draws primarily
  on Source 1, records a claim scoped to image generation only.
- Between sessions: Source 2 is introduced (or the agent encounters it on
  a later, broader crawl)... claim conflict flagged per the architecture's
  contradiction mechanism (Section 5): new claim doesn't just disagree, it
  supersedes the earlier one's scope.
- Session 2: agent researches "Crynux's current node architecture" (same
  query pattern, later), retrieves the flagged lesson, deprioritizes
  Source 1 for scope-related claims, verifies against Source 2 and cites
  the broader task scope plus the vssML consensus protocol by name.

## Crynux — supporting sources (not part of the drift pair, general corpus depth)

- https://github.com/crynux-network/crynux-node: official node source
  repository (domain: github.com, type: official_docs)
- https://docs.crynux.io/system-design/consensus-protocol: consensus
  protocol detail page (domain: docs.crynux.io, type: official_docs)

## Neptune — general corpus (no drift narrative assigned yet — see flag below)

- https://neptune.cash/whitepaper — original Neptune whitepaper (Szepieniec
  & Værge, 2021). Domain: neptune.cash, type: official_docs.
- https://neptune.cash/ — project site under the "Neptune Cash" name.
  Domain: neptune.cash, type: official_docs.
- https://neptune.io/ — project site under the "Neptune Privacy" name,
  ticker $XNT. Domain: neptune.io, type: official_docs.
- https://neptune.io/learn/mutator-set — technical explainer on Mutator
  Sets. Domain: neptune.io, type: official_docs.
- https://talk.neptune.cash/t/mutator-sets-and-their-application-to-scalable-privacy/26
  — community/forum technical note, originally a 2023 blog post. Domain:
  talk.neptune.cash, type: community.

**Resolved:** Neptune Cash (NPT) and Neptune Privacy (XNT) are two distinct,
separately-tracked projects; Neptune Privacy is a community fork of
Neptune Cash, not a rebrand. Confirmed by SafeTrade's official facilitated
swap announcement (Nov 2025), which describes Neptune Privacy as "a
community-built fork" of Neptune Cash and explicitly notes both projects
continue to exist and be supported separately (NPT holders choose one or
the other, not both). The `xnt-core` reference implementation on GitHub
independently confirms this, describing itself as "derived from Neptune
Cash." Fork motivation per project commentary: tokenomics — Neptune Cash's
emissions increase after three years, while Neptune Privacy targets
decreasing emissions for scarcity.

Practical implication for this corpus: `neptune.cash` and `neptune.io`
sources are NOT interchangeable or duplicative — they describe two
separate chains that happen to share ancestry and overlapping cryptographic
design (both inherit zk-STARKs, Mutator Sets, Triton VM from the pre-fork
codebase). Tag sources by their actual project (`neptune_cash` vs.
`neptune_privacy`) rather than merging them under one project value, since
a claim sourced from `neptune.cash` about NPT-chain specifics does not
automatically hold for XNT, and vice versa — treating them as one project
would itself be a source-conflation bug, not a research finding.

## Not yet included

Tokenomics-specific and community/social sources for either project... 