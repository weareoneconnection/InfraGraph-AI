"""Ephemeral competition sandbox; it never writes to the production graph."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from .extract import extract

AMBIGUOUS_TEXT = "巡检发现P70和P71墩存在裂缝和剥落。"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SandboxError(RuntimeError):
    pass


class DemoSandbox:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}

    def create(self) -> dict:
        sid = "SBX-" + secrets.token_hex(4).upper()
        result = extract(AMBIGUOUS_TEXT)
        relations = [{"id": i + 1, "subject": r.subject, "predicate": r.predicate, "object": r.object,
                      "quote": r.quote, "confidence": r.confidence, "status": "PENDING_REVIEW"}
                     for i, r in enumerate(result.relations)]
        state = {"id": sid, "isolated": True, "source": {"ref": "QA-WALK-DEMO", "version": "1.0", "text": AMBIGUOUS_TEXT},
                 "relations": relations, "release": None, "audit": []}
        self.sessions[sid] = state
        self._audit(state, "INGEST", "演示操作者", "4 条歧义关系进入复核队列")
        return self.view(sid)

    def _state(self, sid: str) -> dict:
        if sid not in self.sessions:
            raise KeyError(sid)
        return self.sessions[sid]

    @staticmethod
    def _audit(state: dict, action: str, actor: str, detail: str) -> None:
        state["audit"].append({"action": action, "actor": actor, "detail": detail, "at": _now()})

    def view(self, sid: str) -> dict:
        state = self._state(sid)
        pending = sum(r["status"] == "PENDING_REVIEW" for r in state["relations"])
        gates = {"provenance": {"passed": True, "checked": len(state["relations"])},
                 "ontology_conformance": {"passed": True, "checked": len(state["relations"])},
                 "review_queue_empty": {"passed": pending == 0, "pending": pending}, "has_content": {"passed": True}}
        return {**state, "gates": gates, "stage": "PUBLISHED" if state["release"] else "READY_TO_PUBLISH" if pending == 0 else "REVIEW_REQUIRED"}

    def try_release(self, sid: str, actor: str) -> dict:
        state = self._state(sid)
        pending = sum(r["status"] == "PENDING_REVIEW" for r in state["relations"])
        if pending:
            self._audit(state, "RELEASE_BLOCKED", actor, f"发布闸门阻断：仍有 {pending} 条待复核关系")
            return {**self.view(sid), "blocked": True}
        return self.publish(sid, "demo-r1", actor)

    def review(self, sid: str, relation_id: int, decision: str, actor: str) -> dict:
        state = self._state(sid)
        if len(actor.strip()) < 2:
            raise SandboxError("需要具名复核人")
        relation = next((r for r in state["relations"] if r["id"] == relation_id), None)
        if not relation or relation["status"] != "PENDING_REVIEW":
            raise SandboxError("关系不在待复核队列")
        relation["status"] = "ACCEPTED" if decision == "accept" else "REJECTED"
        relation["reviewed_by"] = actor
        self._audit(state, "REVIEW", actor, f"{decision.upper()} relation:{relation_id}")
        return self.view(sid)

    def apply_recommended_review(self, sid: str, actor: str) -> dict:
        state = self._state(sid)
        for relation in state["relations"]:
            if relation["status"] == "PENDING_REVIEW":
                decision = "accept" if relation["subject"] == "Asset:P70" and relation["object"] == "Defect:crack" else "reject"
                self.review(sid, relation["id"], decision, actor)
        return self.view(sid)

    def publish(self, sid: str, version: str, actor: str) -> dict:
        state = self._state(sid)
        view = self.view(sid)
        if not all(g["passed"] for g in view["gates"].values()):
            raise SandboxError("发布闸门未通过")
        manifest = {"source": state["source"], "relations": [r for r in state["relations"] if r["status"] == "ACCEPTED"]}
        digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        state["release"] = {"version": version, "manifest_hash": digest, "published_by": actor, "at": _now()}
        self._audit(state, "RELEASE", actor, f"发布 {version} · sha256 {digest[:16]}…")
        return self.view(sid)
