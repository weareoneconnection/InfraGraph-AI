"""Stage 12 competition features: structured provenance, reasoning, governance and sandbox."""
from fastapi.testclient import TestClient

from app.parser import parse_document


def test_structure_aware_csv_parser_keeps_row_locators():
    parsed = parse_document("inspection.csv", "构件,问题\nP52,裂缝".encode())
    assert parsed.format == "CSV" and parsed.tables == 2
    assert parsed.blocks[1].locator == "CSV · 表格 2"
    assert parsed.blocks[1].text == "P52 | 裂缝"


def test_search_explains_hybrid_score_and_source_location(kg):
    result = kg.search("P52 墩柱裂缝怎么处理", top_k=1)[0]
    assert result["locator"] and result["score_breakdown"]["bm25"] > 0
    assert {"entity_link", "graph_expansion", "semantic_overlap"} <= set(result["score_breakdown"])


def test_multi_hop_path_has_evidence_on_every_edge(kg):
    path = kg.path("Asset:P52", "Measure:epoxy injection", 4)
    assert path["found"] and path["hops"] == 2
    assert all(edge["evidence"] and edge["evidence"][0]["quote"] for edge in path["edges"])


def test_governance_has_audit_roles_and_signature(kg):
    kg.ingest(ref="AUDIT-1", title="audit", content="P90墩发现裂缝，须采用环氧注浆修补。", actor="资料员 李工")
    governance = kg.governance()
    assert governance["audit"][0]["action"] == "INGEST"
    assert "release" in governance["roles"]["knowledge_publisher"]
    release = kg.release("stage12-r1", "知识管理员 王工")
    assert release["signature"]["algorithm"] in {"HMAC-SHA256", "SHA256-CHECKSUM"}


def test_graph_counts_are_explicit(kg):
    metrics = kg.metrics()
    visible = kg.graph(include_pending=False)
    assert metrics["connected_entities"] == len(visible["nodes"])
    assert metrics["deduplicated_relations"] == len(visible["edges"])


def test_isolated_demo_sandbox_blocks_then_publishes():
    from app.main import app
    with TestClient(app) as client:
        session = client.post("/sandbox/sessions").json()
        sid = session["id"]
        assert session["isolated"] and session["stage"] == "REVIEW_REQUIRED"
        blocked = client.post(f"/sandbox/sessions/{sid}/try-release", json={"actor": "知识管理员 王工"}).json()
        assert blocked["blocked"] and not blocked["gates"]["review_queue_empty"]["passed"]
        reviewed = client.post(f"/sandbox/sessions/{sid}/recommended-review", json={"actor": "知识管理员 王工"}).json()
        assert reviewed["stage"] == "READY_TO_PUBLISH"
        published = client.post(f"/sandbox/sessions/{sid}/publish", json={"actor": "知识管理员 王工"}).json()
        assert published["stage"] == "PUBLISHED" and len(published["release"]["manifest_hash"]) == 64


def test_evaluation_and_governance_endpoints():
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/evaluation").json()["status"] == "PASSED"
        assert client.get("/governance").status_code == 200
