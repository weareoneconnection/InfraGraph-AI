import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("INFRAGRAPH_DB", tempfile.mktemp(suffix=".db"))
for key in ("INFRAGRAPH_MODEL_BASE_URL", "INFRAGRAPH_MODEL"):
    os.environ.pop(key, None)

from app.service import KnowledgeGraph  # noqa: E402
from app.store import Store  # noqa: E402

CORPUS = [json.loads(x) for x in (ROOT / "data" / "corpus.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
FIELDS = ("ref", "title", "content", "version", "authority", "jurisdiction", "domain", "lifecycle")


@pytest.fixture
def kg(tmp_path):
    graph = KnowledgeGraph(Store(tmp_path / "kg.db"))
    for d in CORPUS:
        graph.ingest(**{k: d[k] for k in FIELDS})
    return graph
