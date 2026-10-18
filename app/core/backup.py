"""Sauvegarde automatique des photos validées vers un second dossier (clé USB, disque externe, dossier synchronisé...).

Les photos à sauvegarder sont notées dans data/sauvegarde.jsonl. Un thread les copie au fil de l'eau ; si la destination
est indisponible (clé débranchée), il réessaie toutes les quelques secondes. Rien n'est perdu au redémarrage : le journal
est relu et les photos déjà copiées (même taille) sont simplement reconnues.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..config import Config
from .slideshow_log import SlideshowLog

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackupStats:
    enabled: bool
    copied: int
    pending: int
    last_error: str
    destination: str


class BackupService:
    def __init__(self, config: Config, journal: SlideshowLog | None = None, poll_seconds: float = 10.0) -> None:
        self._config = config
        self._journal = journal or SlideshowLog(config.dossier_donnees / "sauvegarde.jsonl", config.base_dir)
        self._poll = poll_seconds
        self._todo: list[Path] = []
        self._copied = 0
        self._last_error = ""
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- cycle de vie ----------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            self._todo = list(self._journal.load())
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sauvegarde-photos", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def retry_now(self) -> None:
        self._wake.set()

    # ---------- côté interface ----------

    @property
    def enabled(self) -> bool:
        return self._config.sauvegarde_active and self._config.dossier_sauvegarde is not None

    def add(self, paths: Iterable[Path]) -> None:
        """Photos validées à sauvegarder (la bande et ses poses, ou la photo unique)."""
        if not self.enabled:
            return
        for path in paths:
            path = Path(path)
            try:
                self._journal.append(path)
            except OSError:
                log.exception("Journal de sauvegarde inaccessible : %s sera sauvegardée tant que le logiciel tourne", path)
            with self._lock:
                if path not in self._todo:
                    self._todo.append(path)
        self._wake.set()

    def stats(self) -> BackupStats:
        with self._lock:
            pending = len(self._todo)
        destination = self._config.dossier_sauvegarde
        return BackupStats(self.enabled, self._copied, pending, self._last_error, str(destination or ""))

    # ---------- thread de copie ----------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.process()
            except Exception:
                log.exception("Erreur dans le thread de sauvegarde")
            self._wake.wait(self._poll)
            self._wake.clear()

    def _target(self, path: Path, destination: Path) -> Path:
        try:
            relative = path.relative_to(self._config.dossier_photos)     # garde l'arborescence AAAA-MM-JJ/ et poses/
        except ValueError:
            relative = Path(path.name)
        return destination / relative

    def process(self) -> int:
        """Copie ce qui n'est pas encore sauvegardé. Renvoie le nombre de photos copiées pendant ce passage."""
        destination = self._config.dossier_sauvegarde
        if destination is None or not self._config.sauvegarde_active:
            return 0
        copied = 0
        with self._lock:
            todo = list(self._todo)
        for path in todo:
            if self._stop.is_set():
                break
            try:
                if not path.is_file():                                   # supprimée entre-temps (« Recommencer »)
                    self._forget(path)
                    continue
                target = self._target(path, destination)
                if target.is_file() and target.stat().st_size == path.stat().st_size:
                    self._forget(path)                                   # déjà sauvegardée (relance du logiciel)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".tmp")
                shutil.copy2(path, tmp)
                os.replace(tmp, target)
            except OSError as exc:
                self._last_error = str(exc)
                log.warning("Sauvegarde impossible vers %s : %s", destination, exc)
                return copied                                            # destination injoignable : on réessaiera
            self._forget(path)
            self._copied += 1
            copied += 1
        self._last_error = ""
        return copied

    def _forget(self, path: Path) -> None:
        with self._lock:
            if path in self._todo:
                self._todo.remove(path)
