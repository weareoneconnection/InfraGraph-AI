#!/usr/bin/env python3
"""InfraGraph benchmark on the annotated synthetic corpus.

Metrics: relation precision / recall / F1 against gold triples; cross-lingual
entity linking (gold entities seen in both Chinese and English text resolve to
one node); retrieval Recall@3 and MRR over Chinese and English queries,
including cross-lingual ones; claim verification accuracy over SUPPORTED /
CONTRADICTED / INSUFFICIENT_EVIDENCE; version resolution after a source is
revised; provenance completeness; and that a release is blocked while review
is pending. Deterministic (no model).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.service import KnowledgeGraph, ReleaseBlocked  # noqa: E402
from app.store import Store  # noqa: E402

GOLD = json.loads((BASE / "evals" / "gold.json").read_text(encoding="utf-8"))
GATES = {"relation_f1": 0.85, "cross_lingual_linking": 1.0, "retrieval_recall_at_3": 0.9, "retrieval_mrr": 0.8,
         "claim_accuracy": 0.9, "version_resolution": 1.0, "provenance_completeness": 1.0, "release_governance": 1.0}


def load(kg: KnowledgeGraph) -> None:
    for line in (BASE / "data" / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            kg.ingest(**{k: d[k] for k in ("ref", "title", "content", "version", "authority", "jurisdiction", "domain", "lifecycle")})


def relation_scores(kg: KnowledgeGraph) -> dict:
    tp = fp = fn = 0
    per_doc = {}
    for ref, gold in GOLD["relations"].items():
        got = {f"{r['subject']}|{r['predicate']}|{r['object']}" for r in kg.source(ref)["relations"] if r["status"] != "REJECTED"}
        g = set(gold)
        tp += len(got & g); fp += len(got - g); fn += len(g - got)
        per_doc[ref] = {"false_positive": sorted(got - g), "missed": sorted(g - got)}
    p, r = tp / max(1, tp + fp), tp / max(1, tp + fn)
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / max(1e-9, p + r), 3), "tp": tp, "fp": fp, "fn": fn,
            "errors": {k: v for k, v in per_doc.items() if v["false_positive"] or v["missed"]}}


def main() -> int:
    kg = KnowledgeGraph(Store(tempfile.mktemp(suffix=".db")))
    load(kg)
    rel = relation_scores(kg)

    linked = [k for k in GOLD["cross_lingual_entities"] if kg.entity(k)["cross_lingual"]]
    cross = len(linked) / len(GOLD["cross_lingual_entities"])

    hits, rr, retrieval = 0, 0.0, []
    for case in GOLD["retrieval"]:
        refs = list(dict.fromkeys(p["ref"] for p in kg.search(case["q"], top_k=10)))
        top3 = refs[:3]
        ok = any(e in top3 for e in case["expect"])
        rank = next((i + 1 for i, r in enumerate(refs) if r in case["expect"]), None)
        hits += ok; rr += 1 / rank if rank else 0
        retrieval.append({"q": case["q"], "ok": ok, "top3": top3})
    n = len(GOLD["retrieval"])

    claims = []
    for case in GOLD["claims"]:
        verdict = kg.verify_claim(case["text"])["verdict"]
        claims.append({"text": case["text"], "expect": case["expect"], "got": verdict, "ok": verdict == case["expect"]})
    claim_acc = sum(c["ok"] for c in claims) / len(claims)

    # version resolution: revise a source, the new text wins and history stays
    kg.ingest(ref="QA-NCR-0042", title="P52墩柱裂缝不符合项报告", version="2.0", jurisdiction="MY", domain="quality",
              content="P52墩柱裂缝已采用环氧注浆修补完成。\n复检合格，经监理工程师批准关闭NCR-0042。")
    src = kg.source("QA-NCR-0042")
    top = kg.search("P52 裂缝 修补", top_k=3)
    version_ok = (src["current_version"] == "2.0" and len(src["versions"]) == 2
                  and src["versions"][0]["status"] == "SUPERSEDED" and top and top[0]["version"] == "2.0"
                  and all(not (p["ref"] == "QA-NCR-0042" and p["version"] == "1.0") for p in kg.search("P52 裂缝 修补", top_k=10)))

    gates = kg.gates()
    provenance = 1.0 if gates["provenance"]["passed"] else 0.0
    # release governance: pending review blocks; a named human clears it; then a release publishes with a hash
    # An ambiguous sentence (two piers, two defects, no cue) must go to human review, not straight into the graph.
    kg.ingest(ref="QA-WALK-09", title="巡检记录", version="1.0", jurisdiction="MY", domain="quality",
              content="巡检发现P70和P71墩存在裂缝和剥落。")
    pending = kg.review_queue()
    blocked = False
    try:
        kg.release("2026.10-r1", "知识管理员 王工")
    except ReleaseBlocked:
        blocked = True
    for item in pending:
        kg.review(item["id"], "accept" if item["subject"] == "Asset:P70" else "reject", "知识管理员 王工")
    release = kg.release("2026.10-r1", "知识管理员 王工")
    governance_ok = blocked and len(pending) == 4 and len(release["manifest_hash"]) == 64 and kg.releases()[0]["intact"]

    metrics = {"relation_precision": rel["precision"], "relation_recall": rel["recall"], "relation_f1": rel["f1"],
               "cross_lingual_linking": round(cross, 3), "retrieval_recall_at_3": round(hits / n, 3), "retrieval_mrr": round(rr / n, 3),
               "claim_accuracy": round(claim_acc, 3), "version_resolution": 1.0 if version_ok else 0.0,
               "provenance_completeness": provenance, "release_governance": 1.0 if governance_ok else 0.0}
    passed = all(metrics[k] >= v for k, v in GATES.items())
    print(json.dumps({"suite": "INFRAGRAPH_BENCHMARK", "version": "2.0", "dataset": GOLD["version"], "status": "PASSED" if passed else "FAILED",
                      "sizes": {"documents": len(GOLD["relations"]), "gold_relations": sum(len(v) for v in GOLD["relations"].values()),
                                "retrieval_queries": n, "claims": len(claims), "cross_lingual_entities": len(GOLD["cross_lingual_entities"])},
                      "metrics": metrics, "gates": GATES, "relation_errors": rel["errors"],
                      "retrieval": [r for r in retrieval if not r["ok"]], "claims": [c for c in claims if not c["ok"]],
                      "release": {k: release[k] for k in ("version", "manifest_hash", "counts")}, "graph": kg.metrics()},
                     ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
