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
  source_type       STRING,                  
  project           STRING NOT NULL,         
  reliability_score FLOAT DEFAULT 0.5,
  times_used        INT DEFAULT 0,
  successful_uses   INT DEFAULT 0,
  problematic_uses  INT DEFAULT 0,
  last_evaluated    TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT now(),

  INDEX (project, domain)
);

CREATE TABLE episodes (
  episode_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),  
  project       STRING NOT NULL,
  query         STRING NOT NULL,
  strategy      STRING,
  status        STRING DEFAULT 'in_progress',  
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


CREATE TABLE claims (
  claim_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id     UUID REFERENCES episodes(episode_id),
  source_id      UUID REFERENCES sources(source_id),
  project        STRING NOT NULL,
  text           STRING NOT NULL,
  embedding      VECTOR(1024),
  confidence     FLOAT,
  superseded_by  UUID REFERENCES claims(claim_id),  
  created_at     TIMESTAMPTZ DEFAULT now(),

  VECTOR INDEX (project, embedding)
);

CREATE TABLE lessons (
  lesson_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id  UUID REFERENCES episodes(episode_id),
  source_id   UUID REFERENCES sources(source_id),  
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


