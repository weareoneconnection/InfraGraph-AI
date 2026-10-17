from __future__ import annotations
import os, sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH=Path(os.getenv('INFRAGRAPH_DB','./data/infragraph.db'))
SCHEMA=r'''
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS documents(
 id TEXT PRIMARY KEY,
 title TEXT NOT NULL,
 source_ref TEXT UNIQUE NOT NULL,
 authority TEXT,
 jurisdiction TEXT,
 lifecycle_stage TEXT,
 domain TEXT,
 version TEXT,
 content_hash TEXT NOT NULL,
 content TEXT NOT NULL,
 status TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets(
 id TEXT PRIMARY KEY,
 asset_type TEXT NOT NULL,
 canonical_name TEXT NOT NULL,
 normalized_name TEXT NOT NULL,
 properties TEXT NOT NULL,
 source_ref TEXT NOT NULL,
 confidence REAL NOT NULL,
 provenance_complete INTEGER NOT NULL,
 status TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relations(
 id TEXT PRIMARY KEY,
 subject_id TEXT NOT NULL,
 predicate TEXT NOT NULL,
 object_id TEXT NOT NULL,
 source_ref TEXT NOT NULL,
 confidence REAL NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(subject_id,predicate,object_id,source_ref)
);
CREATE TABLE IF NOT EXISTS claims(
 id TEXT PRIMARY KEY,
 text TEXT NOT NULL,
 status TEXT NOT NULL,
 evidence_refs TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases(
 id TEXT PRIMARY KEY,
 version TEXT UNIQUE NOT NULL,
 manifest_hash TEXT NOT NULL,
 asset_count INTEGER NOT NULL,
 relation_count INTEGER NOT NULL,
 status TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
 asset_id UNINDEXED,
 canonical_name,
 asset_type,
 source_ref,
 body,
 tokenize='unicode61'
);
'''

def connect():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB_PATH,check_same_thread=False)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    with connect() as c:
        c.executescript(SCHEMA); c.commit()

@contextmanager
def tx():
    c=connect()
    try:
        yield c; c.commit()
    except Exception:
        c.rollback(); raise
    finally:c.close()
