import sqlite3

import pytest

from app.service import ReleaseBlocked, ReviewError


def test_cross_lingual_search_finds_the_other_language(kg):
    refs = [p["ref"] for p in kg.search("crack on Pier P52 repair method", top_k=3)]
    assert "QA-NCR-0042" in refs  # Chinese NCR found from an English query through entity linking
    assert kg.search("P52 蜂窝麻面", top_k=1)[0]["ref"] == "QA-INS-P52"


def test_entities_are_linked_across_languages(kg):
    p52 = kg.entity("Asset:P52")
    assert p52["cross_lingual"] and {"QA-NCR-0042", "QA-INS-P52"} <= set(p52["sources"])


def test_evidence_must_be_about_the_named_asset(kg):
    result = kg.verify_claim("Edge protection at P47 is optional")
    assert result["verdict"] == "CONTRADICTED" and {e["ref"] for e in result["evidence"]} == {"HSE-MS-P47"}


@pytest.mark.parametrize("claim, verdict", [
    ("P52墩柱裂缝须采用环氧注浆修补", "SUPPORTED"),
    ("P52 pier crack requires no corrective action and can be closed immediately", "CONTRADICTED"),
    ("工期延长须在事件发生后7天内通知", "CONTRADICTED"),
    ("TUN-01 tunnel ventilation fans require monthly maintenance", "INSUFFICIENT_EVIDENCE"),
])
def test_claim_verification(kg, claim, verdict):
    result = kg.verify_claim(claim)
    assert result["verdict"] == verdict
    if verdict != "INSUFFICIENT_EVIDENCE":
        assert result["evidence"]
        # the deciding passage is about the same thing the claim names
        assert all(set(e["document_entities"]) & set(result["claim_entities"]) for e in result["evidence"])


def test_new_version_supersedes_and_keeps_history(kg):
    kg.ingest(ref="QA-NCR-0042", title="NCR", version="2.0", content="P52墩柱裂缝已采用环氧注浆修补完成，复检合格。")
    src = kg.source("QA-NCR-0042")
    assert [v["status"] for v in src["versions"]] == ["SUPERSEDED", "CURRENT"]
    assert all(p["version"] == "2.0" for p in kg.search("P52 裂缝", top_k=10) if p["ref"] == "QA-NCR-0042")


def test_same_content_is_idempotent_and_conflicting_version_rejected(kg):
    d = kg.source("HSE-MS-P47")
    again = kg.ingest(ref="HSE-MS-P47", title="x", content=kg.store.one("SELECT content FROM versions WHERE ref='HSE-MS-P47'")["content"])
    assert again["unchanged"] and len(again["versions"]) == len(d["versions"])
    with pytest.raises(ValueError):
        kg.ingest(ref="HSE-MS-P47", title="x", version="1.0", content="P47墩临边防护已完成整改并复检合格。")


def test_release_requires_review_provenance_and_a_human(kg):
    kg.ingest(ref="QA-WALK-09", title="walk", content="巡检发现P70和P71墩存在裂缝和剥落。")
    with pytest.raises(ReleaseBlocked):
        kg.release("r1", "知识管理员 王工")
    with pytest.raises(ReviewError):
        kg.review(kg.review_queue()[0]["id"], "accept", "model:qwen")
    for item in kg.review_queue():
        kg.review(item["id"], "reject", "知识管理员 王工")
    with pytest.raises(ReviewError):
        kg.release("r1", "agent:x")
    first = kg.release("r1", "知识管理员 王工")
    assert len(first["manifest_hash"]) == 64 and first["counts"]["relations"] > 40
    kg.ingest(ref="QA-NEW-01", title="new", content="P80墩发现裂缝，记录于NCR-0090。")
    second = kg.release("r2", "知识管理员 王工")
    assert second["diff"]["previous"] == "r1" and "Asset:P80|HAS_DEFECT|Defect:crack" in second["diff"]["added_relations"]


def test_tampered_quote_fails_the_provenance_gate(kg):
    with sqlite3.connect(kg.store.path) as conn:
        conn.execute("UPDATE relations SET quote='P52墩柱无需修补。' WHERE id=(SELECT MIN(id) FROM relations)")
    gates = kg.gates()
    assert not gates["provenance"]["passed"] and gates["provenance"]["failed"]


def test_tampered_release_manifest_is_detected(kg):
    kg.release("r1", "知识管理员 王工")
    with sqlite3.connect(kg.store.path) as conn:
        conn.execute("UPDATE releases SET manifest=replace(manifest, 'P52', 'P53')")
    assert kg.releases()[0]["intact"] is False


def test_exports(kg):
    assert "<urn:infragraph:HAS_DEFECT>" in kg.export("ntriples")
    assert kg.export("jsonld")["@graph"]
