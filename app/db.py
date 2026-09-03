from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

from app.config import DB_PATH, ensure_dirs

_local = threading.local()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid4().hex


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        ensure_dirs()
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
        init(conn)
    return conn


@contextmanager
def cursor() -> Iterator[sqlite3.Cursor]:
    con = connect()
    cur = con.cursor()
    try:
        yield cur
        con.commit()
    except Exception:
        con.rollback()
        raise


def init(conn: sqlite3.Connection | None = None) -> None:
    con = conn or connect()
    con.executescript(
            """
            CREATE TABLE IF NOT EXISTS captures (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                audio_path TEXT,
                audio_mime TEXT,
                duration_sec REAL,
                transcript TEXT,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY,
                capture_id TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                title TEXT NOT NULL,
                note TEXT NOT NULL,
                status TEXT NOT NULL,
                wrike_task_id TEXT,
                wrike_url TEXT,
                FOREIGN KEY (capture_id) REFERENCES captures(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_proposals_capture ON proposals(capture_id);
            CREATE INDEX IF NOT EXISTS idx_captures_status ON captures(status);
            """
    )
    con.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def create_capture(
    *,
    source: str,
    audio_path: str,
    audio_mime: str,
    duration_sec: float | None,
    capture_id: str | None = None,
) -> dict[str, Any]:
    item = {
        "id": capture_id or new_id(),
        "created_at": utcnow(),
        "source": source,
        "status": "processing",
        "audio_path": audio_path,
        "audio_mime": audio_mime,
        "duration_sec": duration_sec,
        "transcript": None,
        "error_message": None,
    }
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO captures (
                id, created_at, source, status, audio_path, audio_mime,
                duration_sec, transcript, error_message
            ) VALUES (
                :id, :created_at, :source, :status, :audio_path, :audio_mime,
                :duration_sec, :transcript, :error_message
            )
            """,
            item,
        )
    return item


def get_capture(capture_id: str) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM captures WHERE id = ?", (capture_id,))
        return row_to_dict(cur.fetchone())


def update_capture(capture_id: str, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = :{key}" for key in fields)
    fields["id"] = capture_id
    with cursor() as cur:
        cur.execute(f"UPDATE captures SET {assignments} WHERE id = :id", fields)


def list_inbox() -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute(
            """
            SELECT c.*
            FROM captures c
            WHERE c.status IN ('processing', 'error')
               OR (
                    c.status = 'ready'
                    AND EXISTS (
                        SELECT 1 FROM proposals p
                        WHERE p.capture_id = c.id AND p.status = 'pending'
                    )
               )
            ORDER BY c.created_at DESC
            """
        )
        captures = [row_to_dict(row) for row in cur.fetchall()]
    for capture in captures:
        assert capture is not None
        capture["proposals"] = list_proposals(capture["id"])
    return captures  # type: ignore[return-value]


def list_proposals(capture_id: str) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute(
            """
            SELECT * FROM proposals
            WHERE capture_id = ?
            ORDER BY sort_order ASC
            """,
            (capture_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def replace_proposals(capture_id: str, proposals: list[dict[str, str]]) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    with cursor() as cur:
        cur.execute("DELETE FROM proposals WHERE capture_id = ?", (capture_id,))
        for index, proposal in enumerate(proposals):
            item = {
                "id": new_id(),
                "capture_id": capture_id,
                "sort_order": index,
                "title": proposal["title"],
                "note": proposal.get("note", ""),
                "status": "pending",
                "wrike_task_id": None,
                "wrike_url": None,
            }
            cur.execute(
                """
                INSERT INTO proposals (
                    id, capture_id, sort_order, title, note, status,
                    wrike_task_id, wrike_url
                ) VALUES (
                    :id, :capture_id, :sort_order, :title, :note, :status,
                    :wrike_task_id, :wrike_url
                )
                """,
                item,
            )
            created.append(item)
    return created


def get_proposal(proposal_id: str) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
        return row_to_dict(cur.fetchone())


def update_proposal(proposal_id: str, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = :{key}" for key in fields)
    fields["id"] = proposal_id
    with cursor() as cur:
        cur.execute(f"UPDATE proposals SET {assignments} WHERE id = :id", fields)


def discard_pending_for_capture(capture_id: str) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE proposals
            SET status = 'discarded'
            WHERE capture_id = ? AND status = 'pending'
            """,
            (capture_id,),
        )
