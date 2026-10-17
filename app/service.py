"""Knowledge asset factory: ingest → extract → link → review → verify claims → publish releases.

* **Versions.** Re-ingesting a source with new content creates a new version;
  the previous one and its relations become SUPERSEDED but stay queryable.
  Identical content is a no-op, so retries are idempotent.
* **Review.** Relations below the confidence threshold wait for a named human.
* **Retrieval.** BM25 over current sentences (Latin words + CJK bigrams) plus a
  boost for sentences mentioning the entities the query mentions, so a
  Chinese query finds an English source about the same pier or defect.
* **Claims.** A claim is SUPPORTED only by a passage that covers it and agrees
  in polarity and quantities; a passage that waives an obligation the claim
  states (or vice versa), or gives a different number for the same unit, makes
  it CONTRADICTED; otherwise INSUFFICIENT_EVIDENCE.
* **Releases.** Publishing checks provenance (every quote still equals the
  stored source text at its span), ontology conformance and the review queue,
  then freezes a manifest with a SHA-256 and a diff against the last release.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter

from .extract import REVIEW_THRESHOLD, _mentions_in, extract
from .llm import Model
from .ontology import PREDICATE_LABEL, allowed
from .store import Store, now
from .text import polarity, quantities, tokens

HUMAN_FORBIDDEN = ("agent:", "model:", "system", "policy:")


class ReviewError(PermissionError):
    pass


class ReleaseBlocked(RuntimeError):
    def __init__(self, gates: dict):
        super().__init__("release gates failed: " + ", ".join(k for k, v in gates.items() if not v["passed"]))
        self.gates = gates


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _human(actor: str) -> str:
    actor = (actor or "").strip()
    if len(actor) < 2 or actor.lower().startswith(HUMAN_FORBIDDEN):
        raise ReviewError("reviews and releases need a named human")
    return actor


class KnowledgeGraph:
    def __init__(self, store: Store | None = None, model: Model | None = None) -> None:
        self.store = store or Store()
        self.model = model
        self._index: tuple[int, list[dict], list[Counter], Counter, float] | None = None

    # --- ingestion ----------------------------------------------------------------
    def ingest(self, *, ref: str, title: str, content: str, version: str = "1.0", authority: str = "", jurisdiction: str = "",
               domain: str = "", lifecycle: str = "", actor: str = "ingestion") -> dict:
        content = "\n".join(line.strip() for line in content.strip().splitlines() if line.strip())
        if len(content) < 10:
            raise ValueError("document has insufficient extractable text")
        digest = sha(content)
        with self.store.tx() as c:
            source = c.execute("SELECT * FROM sources WHERE ref=?", (ref,)).fetchone()
            if source and source["current_version_id"]:
                current = c.execute("SELECT * FROM versions WHERE id=?", (source["current_version_id"],)).fetchone()
                if current["content_hash"] == digest:
                    return {**self.source(ref), "unchanged": True}
                if c.execute("SELECT 1 FROM versions WHERE ref=? AND version=?", (ref, version)).fetchone():
                    raise ValueError(f"{ref} version {version} already exists with different content; use a new version")
                c.execute("UPDATE versions SET status='SUPERSEDED' WHERE id=?", (current["id"],))
                c.execute("UPDATE relations SET status='SUPERSEDED' WHERE version_id=? AND status!='REJECTED'", (current["id"],))
            if not source:
                c.execute("INSERT INTO sources(ref,title,authority,jurisdiction,domain,lifecycle,created_at) VALUES(?,?,?,?,?,?,?)",
                          (ref, title, authority, jurisdiction, domain, lifecycle, now()))
            else:
                c.execute("UPDATE sources SET title=?,authority=?,jurisdiction=?,domain=?,lifecycle=? WHERE ref=?",
                          (title, authority, jurisdiction, domain, lifecycle, ref))
            result = extract(content, self.model)
            method = "rules+model" if self.model is not None else "rules"
            vid = c.execute("INSERT INTO versions(ref,version,content,content_hash,status,extraction_method,ingested_by,ingested_at) "
                            "VALUES(?,?,?,?,?,?,?,?)", (ref, version, content, digest, "CURRENT", method, actor, now())).lastrowid
            c.execute("UPDATE sources SET current_version_id=? WHERE ref=?", (vid, ref))
            for idx, (start, end, text) in enumerate(result.sentences):
                c.execute("INSERT INTO chunks(version_id,idx,start,end,text) VALUES(?,?,?,?,?)", (vid, idx, start, end, text))
            for m in result.mentions:
                c.execute("INSERT OR IGNORE INTO entities(key,type,canonical,created_at) VALUES(?,?,?,?)", (m.key, m.type, m.canonical, now()))
                c.execute("INSERT INTO mentions(entity_key,version_id,chunk_idx,start,end,surface) VALUES(?,?,?,?,?,?)",
                          (m.key, vid, m.sentence, m.start, m.end, m.surface))
            for r in result.relations:
                status = "ACCEPTED" if r.confidence >= REVIEW_THRESHOLD else "PENDING_REVIEW"
                c.execute("INSERT INTO relations(subject,predicate,object,version_id,chunk_idx,quote,start,end,confidence,method,status) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (r.subject, r.predicate, r.object, vid, r.sentence, r.quote, r.start, r.end,
                                                           r.confidence, r.method, status))
        self._index = None
        return self.source(ref)

    def source(self, ref: str) -> dict:
        src = self.store.one("SELECT * FROM sources WHERE ref=?", (ref,))
        if not src:
            raise KeyError(ref)
        versions = self.store.rows("SELECT id,version,content_hash,status,extraction_method,ingested_by,ingested_at FROM versions WHERE ref=? ORDER BY id", (ref,))
        current = next((v for v in versions if v["status"] == "CURRENT"), None)
        rels = self.store.rows("SELECT * FROM relations WHERE version_id=? ORDER BY id", (current["id"],)) if current else []
        ents = self.store.rows("SELECT DISTINCT e.key,e.type,e.canonical FROM mentions m JOIN entities e ON e.key=m.entity_key "
                               "WHERE m.version_id=? ORDER BY e.type,e.canonical", (current["id"],)) if current else []
        return {**src, "versions": versions, "current_version": current["version"] if current else None,
                "content_hash": current["content_hash"] if current else None, "entities": ents, "relations": rels}

    def sources(self) -> list[dict]:
        return self.store.rows("SELECT s.ref,s.title,s.authority,s.jurisdiction,s.domain,s.lifecycle,v.version,v.content_hash,v.ingested_at,"
                               "(SELECT COUNT(*) FROM versions x WHERE x.ref=s.ref) AS version_count FROM sources s "
                               "JOIN versions v ON v.id=s.current_version_id ORDER BY s.ref")

    # --- retrieval ----------------------------------------------------------------
    def _current_chunks(self):
        if self._index is None:
            chunks = self.store.rows(
                "SELECT c.version_id,c.idx,c.start,c.end,c.text,v.ref,v.version,v.content_hash,s.jurisdiction,s.domain,s.title "
                "FROM chunks c JOIN versions v ON v.id=c.version_id JOIN sources s ON s.ref=v.ref WHERE v.status='CURRENT'")
            mentions = self.store.rows("SELECT m.entity_key,m.version_id,m.chunk_idx FROM mentions m JOIN versions v ON v.id=m.version_id WHERE v.status='CURRENT'")
            by_chunk: dict[tuple, set] = {}
            for m in mentions:
                by_chunk.setdefault((m["version_id"], m["chunk_idx"]), set()).add(m["entity_key"])
            for ch in chunks:
                ch["entities"] = sorted(by_chunk.get((ch["version_id"], ch["idx"]), set()))
            docs = [Counter(tokens(ch["text"])) for ch in chunks]
            df = Counter()
            for d in docs:
                df.update(d.keys())
            avg = sum(sum(d.values()) for d in docs) / max(1, len(docs))
            self._index = (len(chunks), chunks, docs, df, avg)
        return self._index

    def query_entities(self, text: str) -> list[str]:
        return sorted({m.key for m in _mentions_in(text, 0, 0)})

    def search(self, query: str, top_k: int = 5, jurisdiction: str | None = None, min_score: float = 1.0) -> list[dict]:
        n, chunks, docs, df, avg = self._current_chunks()
        terms = set(tokens(query))
        q_entities = set(self.query_entities(query))
        scored = []
        for ch, doc in zip(chunks, docs):
            if jurisdiction and ch["jurisdiction"] not in {jurisdiction, "", "GENERIC"}:
                continue
            length = sum(doc.values())
            score = 0.0
            for t in terms:
                tf = doc.get(t, 0)
                if tf:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    score += idf * tf * 2.4 / (tf + 1.4 * (0.25 + 0.75 * length / avg))
            shared = q_entities & set(ch["entities"])
            score += 2.5 * len(shared)  # entity linking: cross-lingual match on the same pier, defect or clause
            if score >= min_score:
                scored.append((score, ch, sorted(shared)))
        scored.sort(key=lambda x: -x[0])
        out, seen = [], set()
        for score, ch, shared in scored:
            k = (ch["ref"], ch["idx"])
            if k in seen:
                continue
            seen.add(k)
            out.append({"ref": ch["ref"], "title": ch["title"], "version": ch["version"], "content_hash": ch["content_hash"],
                        "sentence": ch["idx"], "start": ch["start"], "end": ch["end"], "text": ch["text"], "entities": ch["entities"],
                        "linked_entities": shared, "score": round(score, 3)})
            if len(out) >= top_k:
                break
        return out

    # --- claim verification -------------------------------------------------------------
    def verify_claim(self, claim: str, jurisdiction: str | None = None) -> dict:
        passages = self.search(claim, top_k=5, jurisdiction=jurisdiction)
        claim_terms = set(tokens(claim))
        claim_entities = set(self.query_entities(claim))
        claim_pol, claim_qty = polarity(claim), quantities(claim)
        assessed = []
        for p in passages:
            p_terms = set(tokens(p["text"]))
            coverage = len(claim_terms & p_terms) / max(1, len(claim_terms))
            entity_overlap = len(claim_entities & set(p["entities"])) / max(1, len(claim_entities)) if claim_entities else 0.0
            p_pol, p_qty = polarity(p["text"]), quantities(p["text"])
            polarity_conflict = claim_pol != 0 and p_pol != 0 and claim_pol != p_pol
            qty_conflict = any(unit in p_qty and not (vals & p_qty[unit]) for unit, vals in claim_qty.items())
            # A passage can contradict only if it is about the same thing: enough shared wording or entities.
            relevant = coverage >= 0.25 or entity_overlap >= 0.3
            assessed.append({**p, "coverage": round(coverage, 2), "entity_overlap": round(entity_overlap, 2),
                             "polarity_conflict": polarity_conflict, "quantity_conflict": qty_conflict, "relevant": relevant})
        contradicting = [a for a in assessed if a["relevant"] and (a["polarity_conflict"] or a["quantity_conflict"])]
        supporting = [a for a in assessed if not a["polarity_conflict"] and not a["quantity_conflict"]
                      and a["coverage"] >= 0.5 and (not claim_entities or a["entity_overlap"] >= 0.5)]
        strength = lambda a: a["coverage"] + a["entity_overlap"]  # noqa: E731
        # The closest passage decides: a weakly related number elsewhere does not overturn a passage that states the claim.
        if contradicting and (not supporting or max(map(strength, contradicting)) >= max(map(strength, supporting))):
            verdict, evidence = "CONTRADICTED", sorted(contradicting, key=strength, reverse=True)[:3]
        elif supporting:
            verdict, evidence = "SUPPORTED", sorted(supporting, key=strength, reverse=True)[:3]
        else:
            verdict, evidence = "INSUFFICIENT_EVIDENCE", [a for a in assessed if a["relevant"]][:2]
        with self.store.tx() as c:
            cid = c.execute("INSERT INTO claims(text,verdict,evidence,created_at) VALUES(?,?,?,?)",
                            (claim, verdict, json.dumps([{k: e[k] for k in ("ref", "version", "sentence", "text")} for e in evidence], ensure_ascii=False), now())).lastrowid
        return {"claim_id": cid, "claim": claim, "verdict": verdict, "claim_entities": sorted(claim_entities), "evidence": evidence}

    # --- graph ----------------------------------------------------------------------
    def _relations(self, statuses=("ACCEPTED", "PENDING_REVIEW")) -> list[dict]:
        marks = ",".join("?" * len(statuses))
        return self.store.rows(f"SELECT r.*, v.ref, v.version FROM relations r JOIN versions v ON v.id=r.version_id WHERE r.status IN ({marks}) ORDER BY r.id", statuses)

    def entity(self, key: str) -> dict:
        ent = self.store.one("SELECT * FROM entities WHERE key=?", (key,))
        if not ent:
            raise KeyError(key)
        surfaces = [r["surface"] for r in self.store.rows("SELECT DISTINCT surface FROM mentions WHERE entity_key=? ORDER BY surface", (key,))]
        rels = [r for r in self._relations() if key in (r["subject"], r["object"])]
        refs = sorted({r["ref"] for r in self.store.rows("SELECT DISTINCT v.ref FROM mentions m JOIN versions v ON v.id=m.version_id WHERE m.entity_key=? AND v.status='CURRENT'", (key,))})
        langs = {("zh" if any("\u4e00" <= ch <= "\u9fff" for ch in r["text"]) else "en") for r in self.store.rows(
            "SELECT c.text FROM mentions m JOIN chunks c ON c.version_id=m.version_id AND c.idx=m.chunk_idx WHERE m.entity_key=?", (key,))}
        return {**ent, "aliases": surfaces, "languages": sorted(langs), "cross_lingual": langs == {"zh", "en"},
                "relations": rels, "sources": refs}

    def graph(self, focus: str | None = None, include_pending: bool = True, limit: int = 400) -> dict:
        rels = self._relations(("ACCEPTED", "PENDING_REVIEW") if include_pending else ("ACCEPTED",))
        if focus:
            hop1 = {r["object"] if r["subject"] == focus else r["subject"] for r in rels if focus in (r["subject"], r["object"])} | {focus}
            rels = [r for r in rels if r["subject"] in hop1 or r["object"] in hop1]
        edges, keys = {}, set()
        for r in rels[:limit]:
            k = (r["subject"], r["predicate"], r["object"])
            e = edges.setdefault(k, {"subject": r["subject"], "predicate": r["predicate"], "label": PREDICATE_LABEL[r["predicate"]],
                                     "object": r["object"], "status": r["status"], "confidence": r["confidence"], "evidence": []})
            e["evidence"].append({"ref": r["ref"], "version": r["version"], "quote": r["quote"], "relation_id": r["id"]})
            if r["status"] == "ACCEPTED":
                e["status"] = "ACCEPTED"
            keys |= {r["subject"], r["object"]}
        nodes = self.store.rows(f"SELECT key,type,canonical FROM entities WHERE key IN ({','.join('?' * len(keys))})", tuple(keys)) if keys else []
        return {"nodes": nodes, "edges": list(edges.values())}

    # --- review -----------------------------------------------------------------------
    def review_queue(self) -> list[dict]:
        return self._relations(("PENDING_REVIEW",))

    def review(self, relation_id: int, decision: str, actor: str) -> dict:
        actor = _human(actor)
        status = {"accept": "ACCEPTED", "reject": "REJECTED"}[decision]
        with self.store.tx() as c:
            cur = c.execute("UPDATE relations SET status=?,reviewed_by=?,reviewed_at=? WHERE id=? AND status='PENDING_REVIEW'",
                            (status, actor, now(), relation_id))
            if cur.rowcount != 1:
                raise KeyError(f"relation {relation_id} is not pending review")
        return self.store.one("SELECT * FROM relations WHERE id=?", (relation_id,))

    # --- releases ----------------------------------------------------------------------
    def gates(self) -> dict:
        current = self._relations(("ACCEPTED",))
        contents = {v["id"]: v["content"] for v in self.store.rows("SELECT id,content FROM versions WHERE status='CURRENT'")}
        types = {e["key"]: e["type"] for e in self.store.rows("SELECT key,type FROM entities")}
        provenance_bad = [r["id"] for r in current if contents.get(r["version_id"], "")[r["start"]:r["end"]] != r["quote"]]
        ontology_bad = [r["id"] for r in current if not allowed(r["predicate"], types.get(r["subject"], ""), types.get(r["object"], ""))]
        pending = len(self.review_queue())
        return {
            "provenance": {"passed": not provenance_bad, "checked": len(current), "failed": provenance_bad},
            "ontology_conformance": {"passed": not ontology_bad, "checked": len(current), "failed": ontology_bad},
            "review_queue_empty": {"passed": pending == 0, "pending": pending},
            "has_content": {"passed": bool(current)},
        }

    def manifest(self) -> dict:
        rels = self._relations(("ACCEPTED",))
        keys = {k for r in rels for k in (r["subject"], r["object"])}
        return {
            "sources": [{"ref": s["ref"], "version": s["version"], "content_hash": s["content_hash"]} for s in self.sources()],
            "entities": sorted(keys),
            "relations": sorted({f"{r['subject']}|{r['predicate']}|{r['object']}|{r['ref']}@{r['version']}|{sha(r['quote'])[:16]}" for r in rels}),
        }

    def release(self, version: str, actor: str) -> dict:
        actor = _human(actor)
        gates = self.gates()
        if not all(g["passed"] for g in gates.values()):
            raise ReleaseBlocked(gates)
        manifest = self.manifest()
        digest = sha(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        previous = self.store.one("SELECT * FROM releases ORDER BY id DESC LIMIT 1")
        old = json.loads(previous["manifest"]) if previous else {"relations": [], "sources": []}
        triple = lambda s: "|".join(s.split("|")[:3])  # noqa: E731
        old_t, new_t = {triple(x) for x in old["relations"]}, {triple(x) for x in manifest["relations"]}
        old_s = {s["ref"]: s["version"] for s in old["sources"]}
        diff = {"previous": previous["version"] if previous else None, "added_relations": sorted(new_t - old_t),
                "removed_relations": sorted(old_t - new_t),
                "source_changes": sorted(f"{s['ref']}: {old_s.get(s['ref'], '—')} → {s['version']}" for s in manifest["sources"] if old_s.get(s["ref"]) != s["version"])}
        with self.store.tx() as c:
            if c.execute("SELECT 1 FROM releases WHERE version=?", (version,)).fetchone():
                raise ValueError(f"release {version} already exists")
            c.execute("INSERT INTO releases(version,manifest_hash,manifest,diff,gates,published_by,created_at) VALUES(?,?,?,?,?,?,?)",
                      (version, digest, json.dumps(manifest, ensure_ascii=False), json.dumps(diff, ensure_ascii=False),
                       json.dumps(gates), actor, now()))
        return {"version": version, "manifest_hash": digest, "published_by": actor, "counts": {k: len(v) for k, v in manifest.items()},
                "diff": diff, "gates": gates}

    def releases(self) -> list[dict]:
        out = []
        for r in self.store.rows("SELECT * FROM releases ORDER BY id DESC"):
            manifest = json.loads(r["manifest"])
            out.append({"version": r["version"], "manifest_hash": r["manifest_hash"], "published_by": r["published_by"],
                        "created_at": r["created_at"], "counts": {k: len(v) for k, v in manifest.items()}, "diff": json.loads(r["diff"]),
                        "intact": sha(json.dumps(manifest, ensure_ascii=False, sort_keys=True)) == r["manifest_hash"]})
        return out

    def export(self, fmt: str = "jsonld") -> str | dict:
        graph = self.graph(include_pending=False)
        if fmt == "ntriples":
            iri = lambda k: "<urn:infragraph:" + k.replace(" ", "_") + ">"  # noqa: E731
            lines = [f"{iri(n['key'])} <urn:infragraph:type> \"{n['type']}\" ." for n in graph["nodes"]]
            lines += [f"{iri(e['subject'])} <urn:infragraph:{e['predicate']}> {iri(e['object'])} ." for e in graph["edges"]]
            return "\n".join(lines) + "\n"
        return {"@context": {"@vocab": "urn:infragraph:"},
                "@graph": [{"@id": n["key"], "@type": n["type"], "name": n["canonical"],
                            **{e["predicate"]: e["object"] for e in graph["edges"] if e["subject"] == n["key"]}} for n in graph["nodes"]]}

    def metrics(self) -> dict:
        ents = self.store.rows("SELECT key,type FROM entities")
        rels = self.store.rows("SELECT predicate,status,COUNT(*) n FROM relations GROUP BY predicate,status")
        surfaces = self.store.rows("SELECT entity_key, surface FROM mentions")
        langs: dict[str, set] = {}
        for s in surfaces:
            langs.setdefault(s["entity_key"], set()).add("en" if s["surface"].isascii() else "zh")
        gates = self.gates()
        return {
            "sources": len(self.sources()), "versions": self.store.one("SELECT COUNT(*) n FROM versions")["n"],
            "entities": len(ents), "entities_by_type": dict(Counter(e["type"] for e in ents)),
            "cross_lingual_entities": sum(1 for v in langs.values() if v == {"en", "zh"}),
            "relations_by_status": dict(sum((Counter({r["status"]: r["n"]}) for r in rels), Counter())),
            "relations_by_predicate": dict(sum((Counter({r["predicate"]: r["n"]}) for r in rels if r["status"] == "ACCEPTED"), Counter())),
            "provenance_complete": gates["provenance"]["passed"], "pending_review": gates["review_queue_empty"]["pending"],
            "releases": len(self.store.rows("SELECT id FROM releases")),
        }
