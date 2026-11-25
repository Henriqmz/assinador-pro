from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class SignerDatabase:
    """SQLite persistence for documents, signature coordinates, and audit trails."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    original_path TEXT NOT NULL,
                    signed_path TEXT,
                    original_sha256 TEXT NOT NULL,
                    signed_sha256 TEXT,
                    status TEXT NOT NULL,
                    signer_name TEXT,
                    signer_email TEXT,
                    signer_ip TEXT,
                    stamp_page INTEGER NOT NULL DEFAULT 0,
                    stamp_x REAL NOT NULL DEFAULT 58.0,
                    stamp_y REAL NOT NULL DEFAULT 104.0,
                    signed_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            # Lightweight migration for existing databases
            cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
            for col, ddl in [
                ("signer_ip", "TEXT"),
                ("stamp_page", "INTEGER NOT NULL DEFAULT 0"),
                ("stamp_x", "REAL NOT NULL DEFAULT 58.0"),
                ("stamp_y", "REAL NOT NULL DEFAULT 104.0"),
            ]:
                if col not in cols:
                    conn.execute(f"ALTER TABLE documents ADD COLUMN {col} {ddl}")

    def log_event(self, doc_id: str, event_type: str, details: str) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_events (doc_id, event_type, details, created_at) VALUES (?, ?, ?, ?)",
                (doc_id, event_type, details, now),
            )

    def create_document(
        self,
        doc_id: str,
        title: str,
        original_path: str,
        original_sha256: str,
        signer_name: str = "",
        signer_email: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (doc_id, title, original_path, original_sha256, status, signer_name, signer_email, created_at)
                VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?)
                """,
                (doc_id, title, original_path, original_sha256, signer_name, signer_email, now),
            )
        self.log_event(doc_id, "CREATED", f"Documento '{title}' carregado (SHA-256: {original_sha256[:16]}...).")

    def update_stamp_position(self, doc_id: str, page_index: int, x: float, y: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET stamp_page = ?, stamp_x = ?, stamp_y = ? WHERE doc_id = ?",
                (int(page_index), float(x), float(y), doc_id),
            )
        self.log_event(doc_id, "POSITION_UPDATED", f"Campo posicionado na página {page_index + 1} (X={x:.0f}, Y={y:.0f}).")

    def mark_signed(
        self,
        doc_id: str,
        signed_path: str,
        signed_sha256: str,
        signer_name: str,
        signer_email: str,
        signed_at: str,
        signer_ip: str = "127.0.0.1",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE documents
                SET signed_path = ?, signed_sha256 = ?, status = 'SIGNED',
                    signer_name = ?, signer_email = ?, signer_ip = ?, signed_at = ?
                WHERE doc_id = ?
                """,
                (signed_path, signed_sha256, signer_name, signer_email, signer_ip, signed_at, doc_id),
            )
        self.log_event(doc_id, "SIGNED", f"Assinado por {signer_name} <{signer_email}> via IP {signer_ip}.")

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def find_by_hash(self, sha256_hash: str) -> dict[str, Any] | None:
        h = (sha256_hash or "").strip().lower()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE LOWER(signed_sha256) = ? OR LOWER(original_sha256) = ? OR doc_id = ?",
                (h, h, sha256_hash.strip()),
            ).fetchone()
            return dict(row) if row else None

    def list_documents(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM documents ORDER BY created_at DESC")]

    def get_audit_events(self, doc_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT event_type, details, created_at FROM audit_events WHERE doc_id = ? ORDER BY id ASC",
                    (doc_id,),
                )
            ]

    def get_stats(self) -> dict[str, Any]:
        docs = self.list_documents()
        total = len(docs)
        signed = sum(1 for d in docs if d["status"] == "SIGNED")
        pending = total - signed
        rate = round((signed / total) * 100, 1) if total else 0.0
        return {"total": total, "signed": signed, "pending": pending, "completion_rate": rate}
