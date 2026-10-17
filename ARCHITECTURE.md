# Architecture

```text
 Web console · REST API · MCP (official SDK v2)
                    │
            KnowledgeGraph service
 ┌──────────┬───────────┬────────────┬─────────────┬───────────────┐
 Ingest &   Extraction   Retrieval     Claim         Review &
 versions   (rules +     (BM25 over    verification  release gates
 (idempotent validated   sentences +   (coverage,    (provenance,
 by hash)   model)       entity links) polarity,     ontology, queue)
                                       quantities)
 └──────────┴───────────┴────────────┴─────────────┴───────────────┘
                    │
     SQLite: sources · versions · sentences · entities · mentions
             relations (status, quote, span) · claims · releases (manifest, hash, diff)
```

| Module | Responsibility |
| --- | --- |
| `ontology.py` | Types, bilingual lexicon, identifier normalisers, relation domain/range and cues |
| `extract.py` | Sentence split, mentions, clause-nearest attribution, model items validated by quote and ontology |
| `service.py` | Versions, hybrid search, claim verification, graph, review, gates, releases, export, metrics |
| `store.py` | Schema and transactions |
| `text.py` | Tokens (Latin words + CJK bigrams), word-boundary matching, polarity, quantities |
| `main.py` / `mcp_server.py` | REST API / MCP tools |

Production evolution: PostgreSQL + pgvector, a graph store for multi-hop queries, OCR and drawing parsers in front of ingestion, signed release manifests, reviewer identity from the enterprise IdP.
