-- Seed the sources table with the demo corpus curated in
-- src/sources/demo_corpus_manifest.md (Day 2). All URLs/domains are real,
-- verified sources. reliability_score starts at 0.5 (neutral) for every
-- source, by design -- the whole point of the demo is watching that number
-- (and node reliability) move as a *consequence* of real episodes, not
-- seeding it pre-biased.

-- Crynux -- the demo's core drift pair
INSERT INTO sources (url, domain, source_type, project) VALUES
  ('https://docs.crynux.io/system-design/network-architecture', 'docs.crynux.io', 'official_docs', 'crynux'),
  ('https://docs.crynux.io/', 'docs.crynux.io', 'official_docs', 'crynux'),
  ('https://github.com/crynux-network/crynux-node', 'github.com', 'official_docs', 'crynux'),
  ('https://docs.crynux.io/system-design/consensus-protocol', 'docs.crynux.io', 'official_docs', 'crynux');

-- Neptune -- two distinct, related projects (Neptune Privacy is a
-- community fork of Neptune Cash, confirmed via SafeTrade's official
-- swap announcement -- see src/sources/demo_corpus_manifest.md). Tagged
-- by actual project, not merged, since a claim about one chain does not
-- automatically hold for the other despite shared cryptographic ancestry.
INSERT INTO sources (url, domain, source_type, project) VALUES
  ('https://neptune.cash/whitepaper', 'neptune.cash', 'official_docs', 'neptune_cash'),
  ('https://neptune.cash/', 'neptune.cash', 'official_docs', 'neptune_cash'),
  ('https://talk.neptune.cash/t/mutator-sets-and-their-application-to-scalable-privacy/26', 'talk.neptune.cash', 'community', 'neptune_cash'),
  ('https://neptune.io/', 'neptune.io', 'official_docs', 'neptune_privacy'),
  ('https://neptune.io/learn/mutator-set', 'neptune.io', 'official_docs', 'neptune_privacy');
