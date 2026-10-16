"""Envoi des photos par mail en arrière-plan : file d'attente + thread d'envoi qui réessaie jusqu'au succès."""
from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import Config
from .emails import is_valid_email, normalize_email
from .export import ExportResult, export_unsent
from .mail_queue import GUEST, ORGANIZER, PENDING, MailQueue
from .mailer import MailSettings, NetworkError, PermanentMailError, SmtpSender, TemporaryMailError

log = logging.getLogger(__name__)

PROBE_INTERVAL = 30.0      # secondes entre deux vérifications du réseau


def tcp_probe(host: str, port: int, timeout: float = 3.0) -> bool:
    """Le serveur mail est-il joignable ? (simple connexion TCP : rapide, sans rien envoyer)"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass(frozen=True)
class EnqueueResult:
    guest: bool        # un envoi a été mis en file pour l'invité
    organizer: bool    # un envoi a été mis en file pour l'organisateur
    configured: bool   # le compte d'envoi est renseigné dans config.ini


@dataclass(frozen=True)
class MailStats:
    pending: int
    sent: int
    failed: int
    online: bool | None     # None : aucun essai pour l'instant
    configured: bool
    errors: tuple[str, ...] = ()


class MailService:
    def __init__(self, config: Config, queue: MailQueue | None = None,
                 sender_factory: Callable[[MailSettings], SmtpSender] = SmtpSender,
                 clock: Callable[[], float] = time.time, poll_seconds: float = 5.0,
                 connectivity_probe: Callable[[str, int], bool] = tcp_probe,
                 probe_interval: float = PROBE_INTERVAL) -> None:
        self._config = config
        self._queue = queue or MailQueue(config.fichier_envois)
        self._sender_factory = sender_factory
        self._sender = sender_factory(MailSettings.from_config(config))
        self._clock = clock
        self._poll = poll_seconds
        self._online: bool | None = None
        self._probe_fn = connectivity_probe
        self._probe_interval = probe_interval
        self._last_probe: float | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- cycle de vie ----------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="envoi-mails", daemon=True)
        self._thread.start()
        if not self._sender.configured:
            log.warning("Envoi de mails non configuré : renseigne [mail] dans config.ini "
                        "(les photos sont enregistrées, les envois restent en attente)")

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def reload_settings(self) -> None:
        """Après « Recharger la configuration » : le compte d'envoi est relu."""
        self._sender = self._sender_factory(MailSettings.from_config(self._config))
        self._wake.set()

    # ---------- côté interface ----------

    def enqueue_photo(self, photo_path: Path, first_name: str = "", last_name: str = "",
                      guest_email: str = "") -> EnqueueResult:
        """Met la photo en file pour l'invité (s'il a une adresse valide) et pour l'organisateur."""
        guest = normalize_email(guest_email)
        organizer = normalize_email(self._config.adresse_organisateur)
        guest_ok = bool(guest) and is_valid_email(guest)
        organizer_ok = bool(organizer) and is_valid_email(organizer)
        if organizer and not organizer_ok:
            log.warning("adresse_organisateur invalide : %r", organizer)
        if guest_ok:
            self._queue.enqueue(GUEST, guest, photo_path, first_name, last_name, guest)
        copy_for_organizer = organizer_ok and not (guest_ok and guest == organizer)   # pas deux fois la même adresse
        if copy_for_organizer:
            self._queue.enqueue(ORGANIZER, organizer, photo_path, first_name, last_name, guest if guest_ok else "")
        if guest_ok or copy_for_organizer:
            self._wake.set()
        return EnqueueResult(guest_ok, copy_for_organizer, self._sender.configured)

    def retry_now(self) -> int:
        """Mode admin : remet les envois en échec en attente et supprime tous les délais d'attente. Renvoie le nombre remis."""
        count = self._queue.requeue_failed()
        self._queue.make_due_now()
        self._wake.set()
        return count

    def export_unsent(self) -> ExportResult | None:
        """Export de secours des envois non partis (dossier exports/). None s'il n'y en a aucun."""
        return export_unsent(self._queue, self._config.dossier_exports)

    def stats(self) -> MailStats:
        counts = self._queue.counts()
        errors = tuple(self._queue.last_errors())
        return MailStats(counts["pending"], counts["sent"], counts["failed"], self._online,
                         self._sender.configured, errors)

    def requeue_failed(self) -> int:
        count = self._queue.requeue_failed()
        if count:
            self._wake.set()
        return count

    # ---------- thread d'envoi ----------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_due()
                self._probe_if_due()
            except Exception:
                log.exception("Erreur dans le thread d'envoi des mails")
            self._wake.wait(self._poll)
            self._wake.clear()

    # ---------- vérification du réseau ----------

    def _probe_if_due(self) -> None:
        if not self._sender.configured:
            return
        now = self._clock()
        if self._last_probe is not None and now - self._last_probe < self._probe_interval:
            return
        self._last_probe = now
        self.probe()

    def probe(self) -> None:
        """Vérifie que le serveur est joignable, sans attendre qu'un envoi échoue : le voyant et l'écran de fin
        savent ainsi « hors-ligne » avant même l'arrivée du premier invité.

        Un envoi réel reste l'arbitre : si le réseau est revenu alors que des envois attendent, on les relance tout de suite
        et c'est leur résultat qui décide ; sans envoi en attente, on passe directement à « en ligne »."""
        settings = MailSettings.from_config(self._config)
        if not self._probe_fn(settings.host, settings.port):
            if self._online is not False:
                log.warning("Serveur mail injoignable (%s:%s) : hors-ligne", settings.host, settings.port)
            self._online = False
        elif self._online is None:
            self._online = True
        elif self._online is False:
            if self._queue.counts()[PENDING]:
                self._queue.make_due_now()
                self._wake.set()
            else:
                self._online = True
                log.info("Serveur mail de nouveau joignable")

    def process_due(self) -> int:
        """Tente les envois dont l'heure est venue. Renvoie le nombre de mails partis."""
        sender = self._sender
        if not sender.configured:
            return 0
        sent = 0
        while not self._stop.is_set():
            jobs = self._queue.due_jobs()
            if not jobs:
                break
            restarted = False
            for job in jobs:
                if self._stop.is_set():
                    break
                try:
                    sender.send(job)
                except PermanentMailError as exc:
                    self._queue.mark_failed(job.id, str(exc))
                    log.error("Envoi abandonné (%s -> %s) : %s", job.kind, job.recipient, exc)
                    self._online = True               # le serveur a répondu : la connexion fonctionne
                except NetworkError as exc:
                    self._online = False
                    self._queue.mark_retry(job.id, str(exc), network=True)
                    log.warning("Pas de connexion, nouvel essai plus tard : %s", exc)
                    return sent                       # inutile d'essayer les suivants : ils échoueraient pareil
                except TemporaryMailError as exc:
                    self._queue.mark_retry(job.id, str(exc))
                    log.warning("Envoi différé (%s -> %s) : %s", job.kind, job.recipient, exc)
                except Exception as exc:               # imprévu : traité comme provisoire pour ne rien perdre
                    self._queue.mark_retry(job.id, f"Erreur inattendue : {exc!r}")
                    log.exception("Erreur inattendue pendant l'envoi à %s", job.recipient)
                else:
                    self._queue.mark_sent(job.id)
                    sent += 1
                    log.info("Mail envoyé (%s -> %s)", job.kind, job.recipient)
                    if self._online is False:          # le réseau est revenu : on n'attend plus les délais
                        self._queue.make_due_now()
                        restarted = True
                    self._online = True
                    if restarted:
                        break                          # on relit la file : les envois en attente sont maintenant dus
            if not restarted:
                break
        return sent
