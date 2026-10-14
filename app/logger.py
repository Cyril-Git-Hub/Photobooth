"""Journalisation dans logs/photobooth.log (+ console en développement)."""
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:  # déjà configuré
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s : %(message)s")

    file_handler = RotatingFileHandler(
        log_dir / "photobooth.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    if sys.stderr is not None:  # None dans un exécutable PyInstaller sans console
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)

    sys.excepthook = _log_uncaught
    threading.excepthook = _log_thread_exception


def _log_uncaught(exc_type, exc, tb) -> None:
    """Une exception dans un écran est journalisée au lieu de fermer le logiciel."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logging.getLogger("photobooth").critical("Exception non gérée", exc_info=(exc_type, exc, tb))


def _log_thread_exception(args) -> None:
    """Une exception qui s'échappe d'un thread (caméra, envoi des mails...) est journalisée, pas perdue."""
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread is not None else "?"
    logging.getLogger("photobooth").critical(
        "Exception non gérée dans le thread %s", name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
