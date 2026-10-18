"""SQLite schema for sources, versions, sentences, entities, relations, claims and releases."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS sources(ref TEXT PRIMARY KEY, title TEXT NOT NULL, authority TEXT, jurisdiction TEXT,
  domain TEXT, lifecycle TEXT, current_version_id INTEGER, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT NOT NULL REFERENCES sources(ref),
  version TEXT NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL,
  extraction_method TEXT NOT NULL, ingested_by TEXT NOT NULL, ingested_at TEXT NOT NULL, UNIQUE(ref, version));
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, version_id INTEGER NOT NULL REFERENCES versions(id),
  idx INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entities(key TEXT PRIMARY KEY, type TEXT NOT NULL, canonical TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mentions(id INTEGER PRIMARY KEY AUTOINCREMENT, entity_key TEXT NOT NULL REFERENCES entities(key),
  version_id INTEGER NOT NULL REFERENCES versions(id), chunk_idx INTEGER NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
  surface TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS relations(id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, predicate TEXT NOT NULL,
  object TEXT NOT NULL, version_id INTEGER NOT NULL REFERENCES versions(id), chunk_idx INTEGER NOT NULL, quote TEXT NOT NULL,
  start INTEGER NOT NULL, end INTEGER NOT NULL, confidence REAL NOT NULL, method TEXT NOT NULL, status TEXT NOT NULL,
  reviewed_by TEXT, reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS claims(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, verdict TEXT NOT NULL,
  evidence TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS releases(id INTEGER PRIMARY KEY AUTOINCREMENT, version TEXT UNIQUE NOT NULL, manifest_hash TEXT NOT NULL,
  manifest TEXT NOT NULL, diff TEXT NOT NULL, gates TEXT NOT NULL, published_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS document_blocks(id INTEGER PRIMARY KEY AUTOINCREMENT, version_id INTEGER NOT NULL REFERENCES versions(id),
  page INTEGER NOT NULL, block_index INTEGER NOT NULL, kind TEXT NOT NULL, locator TEXT NOT NULL,
  start INTEGER NOT NULL, end INTEGER NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS document_profiles(version_id INTEGER PRIMARY KEY REFERENCES versions(id), format TEXT NOT NULL,
  pages INTEGER NOT NULL, blocks INTEGER NOT NULL, tables INTEGER NOT NULL, ocr_status TEXT NOT NULL, warnings TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, actor TEXT NOT NULL,
  role TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS release_signatures(release_id INTEGER PRIMARY KEY REFERENCES releases(id), algorithm TEXT NOT NULL,
  key_id TEXT NOT NULL, signature TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_mentions_entity ON mentions(entity_key);
CREATE INDEX IF NOT EXISTS ix_relations_status ON relations(status);
CREATE INDEX IF NOT EXISTS ix_blocks_version_span ON document_blocks(version_id,start,end);
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_events(created_at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("INFRAGRAPH_DB", "./data/infragraph.db"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.tx() as c:
            c.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def tx(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rows(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.tx() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        found = self.rows(sql, args)
        return found[0] if found else None
