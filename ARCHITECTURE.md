# Architecture

```text
 Seven-workspace console · REST API · MCP (official SDK v2)
                    │
            KnowledgeGraph service
 ┌──────────┬───────────┬──────────────┬────────────┬──────────────┐
 Structured Extraction   Hybrid search  Graph path   Claim verify
 intake      (rules +    BM25 + entity  reasoning    citations +
 page/block  governed    + graph +      evidence     number checks
 provenance  model)      semantic score per hop      + abstention
 └──────────┴───────────┴──────────────┴────────────┴──────────────┘
                    │
        Review RBAC contract · audit trail · release gates
        signed manifests · isolated competition sandbox
                    │
     SQLite: sources · versions · sentences · entities · mentions
             document blocks/profiles · relations · claims · audit
             releases (manifest, hash, signature, diff)
```

| Module | Responsibility |
| --- | --- |
| `ontology.py` | Types, bilingual lexicon, identifier normalisers, relation domain/range and cues |
| `extract.py` | Sentence split, mentions, clause-nearest attribution, model items validated by quote and ontology |
| `service.py` | Versions, hybrid search, claim verification, graph, review, gates, releases, export, metrics |
| `store.py` | Schema and transactions |
| `parser.py` | TXT/MD/CSV/JSON/PDF/DOCX extraction, page/block locators, OCR-needed detection |
| `text.py` | Tokens (Latin words + CJK bigrams), word-boundary matching, polarity, quantities |
| `main.py` / `mcp_server.py` | REST API / MCP tools |
| `sandbox.py` | Ephemeral, production-isolated review and release demonstration |

Production evolution: PostgreSQL + pgvector, a dedicated graph store, OCR/drawing parsers, enterprise KMS-backed signatures and reviewer identity from the enterprise IdP. The reference implementation exposes these contracts without claiming that the lightweight competition deployment replaces those production services.
