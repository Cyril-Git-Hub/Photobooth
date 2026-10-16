"""File d'attente persistante des envois de mails (SQLite).

Chaque photo donne un envoi par destinataire (l'invité, puis l'organisateur) : une adresse refusée n'empêche
pas l'autre copie de partir. Rien n'est perdu si le réseau tombe ou si le logiciel redémarre : les envois
restent « en attente » dans le fichier jusqu'à leur réussite.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

PENDING, SENT, FAILED = "pending", "sent", "failed"
GUEST, ORGANIZER = "guest", "organizer"
RETRY_DELAYS = (20, 40, 80, 120)    # secondes entre deux essais ; le dernier délai se répète
MAX_ATTEMPTS = 60                   # au-delà, l'envoi est abandonné (journalisé comme échec)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,
    recipient TEXT NOT NULL,
    guest_first_name TEXT NOT NULL DEFAULT '',
    guest_last_name TEXT NOT NULL DEFAULT '',
    guest_email TEXT NOT NULL DEFAULT '',
    photo_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    sent_at REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status, next_attempt_at);
"""


def retry_delay(attempt: int) -> int:
    """Délai avant le prochain essai, après le n-ième échec (1, 2, 3...)."""
    return RETRY_DELAYS[min(max(attempt, 1), len(RETRY_DELAYS)) - 1]


@dataclass(frozen=True)
class UnsentJob:
    """Un envoi qui n'est pas parti, avec ce qu'il faut pour l'exporter."""
    job: "MailJob"
    status: str
    last_error: str
    created_at: float


@dataclass(frozen=True)
class MailJob:
    id: int
    kind: str                 # GUEST ou ORGANIZER
    recipient: str
    guest_first_name: str
    guest_last_name: str
    guest_email: str
    photo_path: Path
    attempts: int

    @property
    def guest_name(self) -> str:
        return f"{self.guest_first_name} {self.guest_last_name}".strip()


class MailQueue:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self._clock = clock
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # une connexion par opération : sûr entre le thread d'envoi et l'interface
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def enqueue(self, kind: str, recipient: str, photo_path: Path, guest_first_name: str = "",
                guest_last_name: str = "", guest_email: str = "") -> int:
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "INSERT INTO jobs (created_at, kind, recipient, guest_first_name, guest_last_name, guest_email, photo_path)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self._clock(), kind, recipient, guest_first_name, guest_last_name, guest_email, str(photo_path)))
            return int(cursor.lastrowid)

    def due_jobs(self, limit: int = 50) -> list[MailJob]:
        """Envois en attente dont l'heure du prochain essai est passée, du plus ancien au plus récent."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM jobs WHERE status = ? AND next_attempt_at <= ? ORDER BY id LIMIT ?",
                                (PENDING, self._clock(), limit)).fetchall()
        return [MailJob(r["id"], r["kind"], r["recipient"], r["guest_first_name"], r["guest_last_name"],
                        r["guest_email"], Path(r["photo_path"]), r["attempts"]) for r in rows]

    def mark_sent(self, job_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE jobs SET status = ?, sent_at = ?, last_error = '' WHERE id = ?",
                         (SENT, self._clock(), job_id))

    def mark_failed(self, job_id: int, error: str) -> None:
        """Échec définitif (adresse refusée, identifiants incorrects...) : plus d'essai automatique."""
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE jobs SET status = ?, attempts = attempts + 1, last_error = ? WHERE id = ?",
                         (FAILED, error, job_id))

    def mark_retry(self, job_id: int, error: str, network: bool = False) -> str:
        """Échec temporaire : nouvel essai plus tard. Renvoie l'état résultant.

        Un refus provisoire du serveur compte dans les essais : après MAX_ATTEMPTS, l'envoi est abandonné.
        Une panne réseau, elle, n'use jamais les essais (`network=True`) : le réseau finira par revenir, et
        l'envoi attend aussi longtemps qu'il le faut, avec le délai maximal entre deux essais.
        """
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT attempts FROM jobs WHERE id = ?", (job_id,)).fetchone()
            previous = row["attempts"] if row else 0
            if network:
                attempts = max(previous, min(previous + 1, len(RETRY_DELAYS)))
            else:
                attempts = previous + 1
            status = FAILED if (not network and attempts >= MAX_ATTEMPTS) else PENDING
            conn.execute("UPDATE jobs SET status = ?, attempts = ?, next_attempt_at = ?, last_error = ? WHERE id = ?",
                         (status, attempts, self._clock() + retry_delay(attempts), error, job_id))
        return status

    def make_due_now(self) -> None:
        """Le réseau est de retour : les envois en attente n'ont plus à patienter."""
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE jobs SET next_attempt_at = 0 WHERE status = ?", (PENDING,))

    def requeue_failed(self) -> int:
        """Remet les envois en échec en attente (après correction d'une adresse expéditeur, par exemple)."""
        with closing(self._connect()) as conn, conn:
            return conn.execute("UPDATE jobs SET status = ?, attempts = 0, next_attempt_at = 0 WHERE status = ?",
                                (PENDING, FAILED)).rowcount

    def unsent_jobs(self, kind: str = GUEST) -> list[UnsentJob]:
        """Envois en attente ou en échec pour ce type de destinataire, du plus ancien au plus récent."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM jobs WHERE status IN (?, ?) AND kind = ? ORDER BY id",
                                (PENDING, FAILED, kind)).fetchall()
        return [UnsentJob(MailJob(r["id"], r["kind"], r["recipient"], r["guest_first_name"], r["guest_last_name"],
                                  r["guest_email"], Path(r["photo_path"]), r["attempts"]),
                          r["status"], r["last_error"], r["created_at"]) for r in rows]

    def counts(self) -> dict[str, int]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
        counts = {PENDING: 0, SENT: 0, FAILED: 0}
        counts.update({r["status"]: r["n"] for r in rows})
        return counts

    def last_errors(self, limit: int = 3) -> list[str]:
        """Dernières erreurs des envois en attente ou en échec (pour le mode administrateur)."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT DISTINCT last_error FROM jobs WHERE status != ? AND last_error != '' "
                                "ORDER BY id DESC LIMIT ?", (SENT, limit)).fetchall()
        return [r["last_error"] for r in rows]
