from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class SignerDatabase:
    """SQLite persistence for documents and cryptographic signature audit trails."""

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
            conn.execute(
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
                    signed_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def create_document(self, doc_id: str, title: str, original_path: str, original_sha256: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (doc_id, title, original_path, original_sha256, status, created_at)
                VALUES (?, ?, ?, ?, 'PENDING', ?)
                """,
                (doc_id, title, original_path, original_sha256, now),
            )

    def mark_signed(
        self,
        doc_id: str,
        signed_path: str,
        signed_sha256: str,
        signer_name: str,
        signer_email: str,
        signed_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE documents
                SET signed_path = ?, signed_sha256 = ?, status = 'SIGNED',
                    signer_name = ?, signer_email = ?, signed_at = ?
                WHERE doc_id = ?
                """,
                (signed_path, signed_sha256, signer_name, signer_email, signed_at, doc_id),
            )

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def list_documents(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM documents ORDER BY created_at DESC")]
