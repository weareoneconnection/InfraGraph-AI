"""Text extraction for uploads: TXT / MD / CSV / JSON, PDF with a text layer, DOCX."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

SUPPORTED = ".txt .md .csv .json .pdf .docx"


def parse_bytes(name: str, content: bytes) -> str:
    ext = Path(name).suffix.lower()
    if ext in {".txt", ".md", ".csv", ".json"}:
        return content.decode("utf-8", errors="replace")
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(content)).pages)
    if ext == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(BytesIO(content)).paragraphs)
    raise ValueError(f"supported formats: {SUPPORTED}")
