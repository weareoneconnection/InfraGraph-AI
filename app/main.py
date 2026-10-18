"""InfraGraph AI API and web console."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import __version__
from .llm import from_env
from .ontology import schema
from .parser import parse_bytes
from .service import KnowledgeGraph, ReleaseBlocked, ReviewError
from .store import Store

BASE = Path(__file__).resolve().parent
DEMO = BASE.parent / "data" / "corpus.jsonl"
kg: KnowledgeGraph | None = None


def graph() -> KnowledgeGraph:
    assert kg is not None
    return kg


@asynccontextmanager
async def lifespan(app: FastAPI):
    global kg
    kg = KnowledgeGraph(Store(), model=from_env())
    yield


app = FastAPI(title="InfraGraph AI", version=__version__, lifespan=lifespan,
              description="Transport infrastructure knowledge asset factory and engineering knowledge graph")


class DocumentIn(BaseModel):
    ref: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=2, max_length=300)
    content: str = Field(min_length=10, max_length=200_000)
    version: str = "1.0"
    authority: str = ""
    jurisdiction: str = ""
    domain: str = ""
    lifecycle: str = ""
    actor: str = "ingestion"


class ClaimIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    jurisdiction: str | None = None


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(accept|reject)$")
    actor: str = Field(min_length=2, max_length=120)


class ReleaseIn(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    actor: str = Field(min_length=2, max_length=120)


def _ingest(**kwargs):
    try:
        return graph().ingest(**kwargs)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/health")
def health():
    m = graph().metrics()
    return {"status": "ok", "product": "InfraGraph AI", "version": __version__,
            "model": graph().model.describe() if graph().model else "rules",
            "sources": m["sources"], "entities": m["entities"], "provenance_complete": m["provenance_complete"]}


@app.get("/ontology")
def ontology():
    return schema()


@app.post("/documents", status_code=201)
def ingest(doc: DocumentIn):
    return _ingest(**doc.model_dump())


@app.post("/documents/upload", status_code=201)
async def upload(file: UploadFile = File(...), ref: str = Form(..., min_length=2, max_length=120),
                 title: str = Form("", max_length=300), version: str = Form("1.0", min_length=1, max_length=40),
                 authority: str = Form(""), jurisdiction: str = Form(""), domain: str = Form(""), lifecycle: str = Form("")):
    data = await file.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "file too large")
    try:
        text = parse_bytes(file.filename or "upload.txt", data)
    except ValueError as exc:
        raise HTTPException(415, str(exc))
    if len(text.strip()) < 10:
        raise HTTPException(422, "文件已接收，但未能提取至少 10 个字符的正文；扫描版 PDF 请先进行 OCR。")
    return _ingest(ref=ref, title=title or file.filename or ref, content=text, version=version, authority=authority,
                   jurisdiction=jurisdiction, domain=domain, lifecycle=lifecycle, actor="upload")


@app.post("/demo/load")
def load_demo():
    loaded = []
    for line in DEMO.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            loaded.append(_ingest(**{k: d[k] for k in ("ref", "title", "content", "version", "authority", "jurisdiction", "domain", "lifecycle")})["ref"])
    return {"loaded": loaded, "metrics": graph().metrics()}


@app.get("/documents")
def documents():
    return graph().sources()


@app.get("/documents/{ref}")
def document(ref: str):
    try:
        return graph().source(ref)
    except KeyError:
        raise HTTPException(404, "source not found")


@app.get("/search")
def search(q: str = Query(min_length=1, max_length=500), limit: int = Query(5, ge=1, le=20), jurisdiction: str | None = None):
    return {"query": q, "query_entities": graph().query_entities(q), "results": graph().search(q, limit, jurisdiction)}


class QuestionIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    jurisdiction: str | None = None


@app.post("/ask")
def ask(payload: QuestionIn):
    return graph().ask(payload.question, payload.jurisdiction)


@app.post("/claims/verify")
def verify(claim: ClaimIn):
    return graph().verify_claim(claim.text, claim.jurisdiction)


@app.get("/entities/{key:path}")
def entity(key: str):
    try:
        return graph().entity(key)
    except KeyError:
        raise HTTPException(404, "entity not found")


@app.get("/graph")
def graph_view(focus: str | None = None, include_pending: bool = True):
    return graph().graph(focus, include_pending)


@app.get("/review")
def review_queue():
    return graph().review_queue()


@app.post("/review/{relation_id}")
def review(relation_id: int, payload: ReviewIn):
    try:
        return graph().review(relation_id, payload.decision, payload.actor)
    except ReviewError as exc:
        raise HTTPException(403, str(exc))
    except KeyError as exc:
        raise HTTPException(409, str(exc).strip("'"))


@app.get("/releases/gates")
def gates():
    return graph().gates()


@app.post("/releases", status_code=201)
def release(payload: ReleaseIn):
    try:
        return graph().release(payload.version, payload.actor)
    except ReviewError as exc:
        raise HTTPException(403, str(exc))
    except ReleaseBlocked as exc:
        raise HTTPException(409, {"message": str(exc), "gates": exc.gates})
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/releases")
def releases():
    return graph().releases()


@app.get("/export")
def export(fmt: str = Query("jsonld", pattern="^(jsonld|ntriples)$")):
    out = graph().export(fmt)
    return PlainTextResponse(out, media_type="application/n-triples") if fmt == "ntriples" else out


@app.get("/metrics")
def metrics():
    return graph().metrics()


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(BASE / "static" / "index.html")
