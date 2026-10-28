"""Persistencia SQLite: sesiones, versiones de procedimiento, ejecuciones y auditoría."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, created_at TEXT, expires_at TEXT, consent_at TEXT);
CREATE TABLE IF NOT EXISTS procedures(id TEXT PRIMARY KEY, session_id TEXT, name TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS procedure_versions(
  procedure_id TEXT, version INTEGER, status TEXT CHECK(status IN ('draft','approved')),
  content_json TEXT, content_hash TEXT, created_at TEXT, PRIMARY KEY(procedure_id, version));
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY, procedure_id TEXT, procedure_version INTEGER, status TEXT, verdict TEXT,
  report_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS model_calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, kind TEXT, model_version TEXT, request_id TEXT,
  latency_ms INTEGER, status TEXT, error TEXT, created_at TEXT);
"""


class Database:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    @contextmanager
    def tx(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def one(self, sql: str, *args):
        return self.conn.execute(sql, args).fetchone()

    def all(self, sql: str, *args):
        return self.conn.execute(sql, args).fetchall()
