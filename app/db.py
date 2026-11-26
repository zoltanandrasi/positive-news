"""SQLite tárolás."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    link          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    title_key     TEXT NOT NULL,
    lead          TEXT NOT NULL DEFAULT '',
    image_url     TEXT,
    source        TEXT NOT NULL,
    category      TEXT NOT NULL,
    published_at  TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    blocked_by    TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_cat_pub ON articles(category, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_pub ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_title_key ON articles(title_key);

CREATE TABLE IF NOT EXISTS feed_status (
    url           TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    last_run_at   TEXT NOT NULL,
    ok            INTEGER NOT NULL,
    items         INTEGER NOT NULL DEFAULT 0,
    added         INTEGER NOT NULL DEFAULT 0,
    blocked       INTEGER NOT NULL DEFAULT 0,
    error         TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # --- írás ---------------------------------------------------------------
    def has_link_or_title(self, con, link: str, title_key: str) -> bool:
        row = con.execute(
            "SELECT 1 FROM articles WHERE link = ? OR title_key = ? LIMIT 1", (link, title_key)
        ).fetchone()
        return row is not None

    def insert_article(self, con, a: dict) -> None:
        con.execute(
            """INSERT OR IGNORE INTO articles
               (link, title, title_key, lead, image_url, source, category, published_at, fetched_at, blocked_by)
               VALUES (:link, :title, :title_key, :lead, :image_url, :source, :category,
                       :published_at, :fetched_at, :blocked_by)""",
            a,
        )

    def save_feed_status(self, con, s: dict) -> None:
        con.execute(
            """INSERT INTO feed_status (url, name, last_run_at, ok, items, added, blocked, error)
               VALUES (:url, :name, :last_run_at, :ok, :items, :added, :blocked, :error)
               ON CONFLICT(url) DO UPDATE SET name=excluded.name, last_run_at=excluded.last_run_at,
                 ok=excluded.ok, items=excluded.items, added=excluded.added,
                 blocked=excluded.blocked, error=excluded.error""",
            s,
        )

    def set_meta(self, con, key: str, value: str) -> None:
        con.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def purge_older_than(self, days: int) -> int:
        cutoff = iso(utcnow() - timedelta(days=days))
        with self.connect() as con:
            cur = con.execute("DELETE FROM articles WHERE published_at < ?", (cutoff,))
            return cur.rowcount

    # --- olvasás ------------------------------------------------------------
    def latest(self, category: str | None = None, limit: int = 30, offset: int = 0) -> list[sqlite3.Row]:
        sql = "SELECT * FROM articles WHERE blocked_by IS NULL"
        args: list = []
        if category:
            sql += " AND category = ?"
            args.append(category)
        sql += " ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self.connect() as con:
            return con.execute(sql, args).fetchall()

    def count(self, category: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM articles WHERE blocked_by IS NULL"
        args: list = []
        if category:
            sql += " AND category = ?"
            args.append(category)
        with self.connect() as con:
            return con.execute(sql, args).fetchone()[0]

    def blocked(self, limit: int = 100) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM articles WHERE blocked_by IS NOT NULL ORDER BY fetched_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def feed_statuses(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute("SELECT * FROM feed_status ORDER BY name").fetchall()

    def get_meta(self, key: str) -> str | None:
        with self.connect() as con:
            row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None
