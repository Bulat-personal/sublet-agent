"""
SQLite-backed dedup store. Adapted from rental-agent/db.py.
Tracks which listing IDs we've already notified about so we don't spam.
State is committed back to the repo by the GitHub Actions workflow.
"""

import sqlite3
import logging
import os

logger = logging.getLogger(__name__)
DB_PATH = os.environ.get("DB_PATH", "state.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            id      TEXT PRIMARY KEY,
            url     TEXT,
            source  TEXT,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"Database initialised at {DB_PATH}")


def is_seen(listing_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM seen WHERE id = ?", (listing_id,))
    found = c.fetchone() is not None
    conn.close()
    return found


def mark_seen(listing_id: str, url: str, source: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO seen (id, url, source) VALUES (?, ?, ?)",
        (listing_id, url, source),
    )
    conn.commit()
    conn.close()


def purge_old(days: int = 45):
    """Remove entries older than `days` so the DB stays lean."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM seen WHERE seen_at < datetime('now', ?)", (f"-{days} days",))
    deleted = conn.total_changes
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Purged {deleted} old entries from DB")


def count() -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM seen")
    n = c.fetchone()[0]
    conn.close()
    return n
