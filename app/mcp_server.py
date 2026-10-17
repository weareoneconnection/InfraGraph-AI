"""MCP server (official MCP Python SDK v2): the knowledge graph as a tool for agents.

Agents can search, verify claims, read entities and neighbours and list
releases. Ingestion, review and publishing stay human operations.
"""
from __future__ import annotations

from mcp.server import MCPServer

from .service import KnowledgeGraph

EXPOSED = ["search_knowledge", "ask_knowledge", "verify_claim", "get_entity", "graph_neighbors", "list_releases"]


def build_server(kg: KnowledgeGraph) -> MCPServer:
    server = MCPServer("InfraGraph AI", version="2.0.0",
                       instructions="Governed transport-infrastructure knowledge graph with sentence-level provenance.")

    @server.tool()
    def search_knowledge(query: str, limit: int = 5) -> dict:
        """Hybrid search (BM25 + entity linking, Chinese and English). Each result cites source, version, hash and sentence."""
        return {"query_entities": kg.query_entities(query), "results": kg.search(query, min(max(limit, 1), 20))}

    @server.tool()
    def ask_knowledge(question: str) -> dict:
        """Grounded answer: a model answer citing only retrieved sentences (numbers checked), else the passages themselves."""
        return kg.ask(question)

    @server.tool()
    def verify_claim(text: str) -> dict:
        """Check an engineering claim: SUPPORTED, CONTRADICTED or INSUFFICIENT_EVIDENCE, with the deciding passages."""
        return kg.verify_claim(text)

    @server.tool()
    def get_entity(key: str) -> dict:
        """An entity such as 'Asset:P52' with its Chinese/English aliases, relations and sources."""
        return kg.entity(key)

    @server.tool()
    def graph_neighbors(key: str) -> dict:
        """One-hop neighbourhood of an entity, with evidence quotes for every edge."""
        return kg.graph(focus=key)

    @server.tool()
    def list_releases() -> list[dict]:
        """Published knowledge releases with manifest hashes and diffs."""
        return kg.releases()

    return server


if __name__ == "__main__":
    import argparse

    from .llm import from_env
    from .store import Store

    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--port", type=int, default=8112)
    args = parser.parse_args()
    server = build_server(KnowledgeGraph(Store(), model=from_env()))
    server.run(transport="streamable-http", port=args.port) if args.transport == "streamable-http" else server.run()
