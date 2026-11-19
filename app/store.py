"""Baza SQLite: klienci, historia ruchu, sesje, dziennik, ustawienia."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clients (
    public_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    private_key TEXT,
    preshared_key TEXT,
    address TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'full',
    dns TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    imported INTEGER NOT NULL DEFAULT 0,
    peer_json TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_key TEXT NOT NULL,
    endpoint TEXT,
    started_at INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    ended_at INTEGER,
    rx INTEGER NOT NULL DEFAULT 0,
    tx INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS sessions_pk ON sessions(public_key, started_at);
CREATE TABLE IF NOT EXISTS traffic (
    ts INTEGER NOT NULL,
    public_key TEXT NOT NULL,
    rx INTEGER NOT NULL,
    tx INTEGER NOT NULL,
    PRIMARY KEY (ts, public_key)
);
CREATE TABLE IF NOT EXISTS usage_daily (
    day TEXT NOT NULL,
    public_key TEXT NOT NULL,
    rx INTEGER NOT NULL,
    tx INTEGER NOT NULL,
    PRIMARY KEY (day, public_key)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    public_key TEXT
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    ip TEXT,
    user_agent TEXT
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)
        try:
            path.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def all(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, args).fetchone()
            return dict(row) if row else None

    def run(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, args)
            return cur.lastrowid or cur.rowcount

    # ------------------------------------------------------------ ustawienia
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.run("INSERT INTO settings(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # ------------------------------------------------------------ dziennik
    def event(self, kind: str, message: str, public_key: str | None = None) -> None:
        self.run("INSERT INTO events(ts,kind,message,public_key) VALUES(?,?,?,?)",
                 (int(time.time()), kind, message, public_key))

    # ------------------------------------------------------------ klienci
    def clients(self) -> list[dict[str, Any]]:
        return self.all("SELECT * FROM clients ORDER BY created_at, name")

    def client(self, public_key: str) -> dict[str, Any] | None:
        return self.one("SELECT * FROM clients WHERE public_key=?", (public_key,))

    def insert_client(self, data: dict[str, Any]) -> None:
        now = int(time.time())
        data = {"note": "", "mode": "full", "enabled": 1, "imported": 0,
                "created_at": now, "updated_at": now, **data}
        if isinstance(data.get("peer_json"), (dict, list)):
            data["peer_json"] = json.dumps(data["peer_json"])
        cols = ",".join(data)
        marks = ",".join("?" for _ in data)
        self.run(f"INSERT INTO clients({cols}) VALUES({marks})", tuple(data.values()))

    def update_client(self, public_key: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = int(time.time())
        if isinstance(fields.get("peer_json"), (dict, list)):
            fields["peer_json"] = json.dumps(fields["peer_json"])
        sets = ",".join(f"{k}=?" for k in fields)
        self.run(f"UPDATE clients SET {sets} WHERE public_key=?", (*fields.values(), public_key))

    def replace_client_key(self, old_key: str, new_key: str) -> None:
        with self.tx() as c:
            c.execute("UPDATE clients SET public_key=? WHERE public_key=?", (new_key, old_key))
            for table in ("sessions", "traffic", "usage_daily", "events"):
                c.execute(f"UPDATE {table} SET public_key=? WHERE public_key=?", (new_key, old_key))

    def delete_client(self, public_key: str, keep_history: bool = True) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM clients WHERE public_key=?", (public_key,))
            if not keep_history:
                for table in ("sessions", "traffic", "usage_daily"):
                    c.execute(f"DELETE FROM {table} WHERE public_key=?", (public_key,))

    # ------------------------------------------------------------ sprzątanie
    def cleanup(self, history_days: int) -> None:
        cutoff = int(time.time()) - history_days * 86400
        day_cutoff = time.strftime("%Y-%m-%d", time.localtime(cutoff - 335 * 86400))
        with self.tx() as c:
            c.execute("DELETE FROM traffic WHERE ts<?", (cutoff,))
            c.execute("DELETE FROM sessions WHERE ended_at IS NOT NULL AND ended_at<?", (cutoff,))
            c.execute("DELETE FROM events WHERE ts<?", (cutoff,))
            c.execute("DELETE FROM usage_daily WHERE day<?", (day_cutoff,))
            c.execute("DELETE FROM auth_sessions WHERE expires_at<?", (int(time.time()),))
