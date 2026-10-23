"""Soirées persistantes et index privé des résultats photo par adresse mail."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ..config import Config

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    started_at REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_single_active ON events(active) WHERE active = 1;
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES events(id),
    email TEXT NOT NULL,
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    photo_path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(event_id, email, photo_path)
);
CREATE INDEX IF NOT EXISTS idx_event_photos ON photos(event_id, email, created_at);
"""


@dataclass(frozen=True)
class Event:
    id: str
    name: str
    started_at: float
    active: bool


@dataclass(frozen=True)
class GuestPhotos:
    email: str
    first_name: str
    last_name: str
    count: int

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email


@dataclass(frozen=True)
class PhotoRecord:
    path: Path
    media_type: str
    created_at: float


class EventStore:
    """Index indépendant de la file de mails ; il reste disponible après redémarrage."""

    def __init__(self, config: Config) -> None:
        self.path = config.dossier_donnees / "soirees.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _event(row: sqlite3.Row | None) -> Event | None:
        if row is None:
            return None
        return Event(row["id"], row["name"], row["started_at"], bool(row["active"]))

    def active_event(self) -> Event | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM events WHERE active = 1").fetchone()
        return self._event(row)

    def list_events(self) -> list[Event]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY started_at DESC").fetchall()
        return [self._event(row) for row in rows if row is not None]

    def start_event(self, now: datetime | None = None) -> Event:
        now = now or datetime.now()
        started_at = now.timestamp()
        event_id = uuid4().hex
        name = f"Soirée du {now:%d/%m/%Y à %H:%M}"
        with closing(self._connect()) as connection, connection:
            connection.execute("UPDATE events SET active = 0 WHERE active = 1")
            connection.execute("INSERT INTO events (id, name, started_at, active) VALUES (?, ?, ?, 1)",
                               (event_id, name, started_at))
        event = Event(event_id, name, started_at, True)
        log.info("Nouvelle soirée démarrée : %s (%s)", name, event_id)
        return event

    def end_event(self) -> Event | None:
        """Cloture la soiree active sans supprimer son historique ni ses photos."""
        with closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT * FROM events WHERE active = 1").fetchone()
            if row is None:
                return None
            connection.execute("UPDATE events SET active = 0 WHERE id = ?", (row["id"],))
        event = Event(row["id"], row["name"], row["started_at"], False)
        log.info("Soiree terminee : %s (%s)", event.name, event.id)
        return event

    def record_photo(self, event_id: str, email: str, first_name: str, last_name: str,
                     path: Path, media_type: str, now: datetime | None = None) -> None:
        email = email.strip().casefold()
        if not email or not event_id or not path.is_file():
            return
        timestamp = (now or datetime.now()).timestamp()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO photos "
                "(event_id, email, first_name, last_name, photo_path, media_type, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, email, first_name.strip(), last_name.strip(), str(path.resolve()), media_type, timestamp),
            )

    def guests(self, event_id: str) -> list[GuestPhotos]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT email, MIN(first_name) AS first_name, MIN(last_name) AS last_name, COUNT(*) AS count "
                "FROM photos WHERE event_id = ? GROUP BY email ORDER BY first_name COLLATE NOCASE, "
                "last_name COLLATE NOCASE, email COLLATE NOCASE", (event_id,)
            ).fetchall()
        return [GuestPhotos(row["email"], row["first_name"], row["last_name"], row["count"]) for row in rows]

    def photos_for_guest(self, event_id: str, email: str) -> list[PhotoRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT photo_path, media_type, created_at FROM photos "
                "WHERE event_id = ? AND email = ? ORDER BY created_at, id", (event_id, email.casefold())
            ).fetchall()
        return [PhotoRecord(Path(row["photo_path"]), row["media_type"], row["created_at"]) for row in rows]
