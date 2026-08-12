-- Agent Black Box — CockroachDB schema
-- CockroachDB v25.2+ required for VECTOR INDEX support.
--
-- Vector index syntax confirmed against current CockroachDB docs
-- (docs/v26.2/vector, docs/stable/create-index) as of this file's creation:
--   VECTOR INDEX (prefix_col, embedding_col) declared inline in CREATE TABLE.
-- The prefix column (project) partitions the index so that a query filtering
-- on project only searches that project's vectors — this is what makes the
-- "structural filter, then vector rank, single query" retrieval pattern in
-- the architecture doc (Section F) actually work as one index, not two
-- systems glued together.
--
-- Six tables total. No graph structure, no separate embeddings table.

CREATE TABLE sources (
  source_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url               STRING,
  domain            STRING NOT NULL,
  source_type       STRING,                  -- official_docs | blog | social | third_party
  project           STRING NOT NULL,         -- 'crynux' | 'neptune_privacy' | ...
  reliability_score FLOAT DEFAULT 0.5,
  times_used        INT DEFAULT 0,
  successful_uses   INT DEFAULT 0,
  problematic_uses  INT DEFAULT 0,
  last_evaluated    TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT now(),

  INDEX (project, domain)
);

CREATE TABLE episodes (
  episode_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- client-generated for idempotent retries
  project       STRING NOT NULL,
  query         STRING NOT NULL,
  strategy      STRING,
  status        STRING DEFAULT 'in_progress',  -- in_progress | completed | failed | pending_persist
  started_at    TIMESTAMPTZ DEFAULT now(),
  completed_at  TIMESTAMPTZ,
  final_answer  STRING,
  metadata      JSONB,

  INDEX (project, started_at)
);

CREATE TABLE episode_sources (
  episode_id  UUID REFERENCES episodes(episode_id),
  source_id   UUID REFERENCES sources(source_id),
  role        STRING,   -- used | rejected | deprioritized
  PRIMARY KEY (episode_id, source_id)
);

-- Embedding dimension: set to match the exact Bedrock embedding model
-- chosen on Day 1 (e.g. Titan Text Embeddings V2 defaults to 1024 but
-- supports 256/512/1024 — pick one and set it here before any rows are
-- written; changing it later means a migration, not a config edit).
CREATE TABLE claims (
  claim_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id     UUID REFERENCES episodes(episode_id),
  source_id      UUID REFERENCES sources(source_id),
  project        STRING NOT NULL,
  text           STRING NOT NULL,
  embedding      VECTOR(1024),
  confidence     FLOAT,
  superseded_by  UUID REFERENCES claims(claim_id),  -- append-only: never overwrite, point forward instead
  created_at     TIMESTAMPTZ DEFAULT now(),

  VECTOR INDEX (project, embedding)
);

CREATE TABLE lessons (
  lesson_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id  UUID REFERENCES episodes(episode_id),
  source_id   UUID REFERENCES sources(source_id),  -- nullable: strategy lessons aren't source-specific
  project     STRING NOT NULL,
  text        STRING NOT NULL,
  embedding   VECTOR(1024),
  confidence  FLOAT,
  created_at  TIMESTAMPTZ DEFAULT now(),

  VECTOR INDEX (project, embedding)
);

CREATE TABLE contradictions (
  contradiction_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id             UUID REFERENCES claims(claim_id),
  conflicting_claim_id UUID REFERENCES claims(claim_id),
  detected_at          TIMESTAMPTZ DEFAULT now(),
  resolved             BOOL DEFAULT false,
  resolution_note      STRING
);

-- Example retrieval query this schema is built for (Section F of the
-- architecture doc) — structural filter first, vector rank second, one
-- round trip:
--
-- SELECT claim_id, text, confidence
-- FROM claims
-- WHERE project = $1
-- ORDER BY embedding <-> $2
-- LIMIT 5;
--
-- Because (project, embedding) is the index's prefix + vector column, this
-- query only searches the given project's partition of the index, not the
-- whole table.
