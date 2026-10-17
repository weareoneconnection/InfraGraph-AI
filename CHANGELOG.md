# Changelog

## 2.0.0 — 2026-10-17
- Ontology with 10 entity types, 9 relations, domain/range constraints and a bilingual lexicon.
- Cross-lingual entity resolution; identifier normalisation for assets, documents, standards and clauses.
- Sentence-level provenance (quote + character span) for every relation; clause-nearest subject attribution.
- Optional model extraction, accepted only with verbatim quotes and ontology-conformant relations.
- Versioned sources: idempotent re-ingestion, superseded versions kept, conflicting versions rejected.
- Hybrid retrieval (BM25 with CJK bigrams + entity linking); Chinese queries find English sources.
- Claim verification with polarity and quantity conflict detection: SUPPORTED / CONTRADICTED / INSUFFICIENT_EVIDENCE.
- Human review queue; release gates (provenance, ontology, review); manifest SHA-256 and release diffs; tamper detection.
- MCP server; JSON-LD and N-Triples export; web console with graph explorer.
- Claim evidence must name the same asset, document, clause or standard as the claim (source-level).
- Annotated evaluation set (incl. deciding-source accuracy) and 23 tests.

## 1.0.0
- Keyword ontology mapping, FTS5 search and release hash.
