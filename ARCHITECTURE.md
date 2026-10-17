# Architecture

```text
Raw Documents / Standards / Contracts / NCR / RFI / Lessons
                         │
                         ▼
                 Ingestion + Parser
                         │
                         ▼
          Extraction + Normalization + Resolution
                         │
                         ▼
              Infrastructure Ontology
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
     Knowledge Graph              Evidence Graph
           │                           │
           └─────────────┬─────────────┘
                         ▼
               Quality / Provenance Gate
                         ▼
                  Knowledge Release
                         ▼
          Search / Claim Verify / MCP / Agents
```

Production evolution: Postgres metadata + object storage + vector index + graph DB + human review workflow + release signing.
