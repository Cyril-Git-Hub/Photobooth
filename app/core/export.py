"""Export de secours des envois qui ne sont pas partis (pas d'internet de la soirée, par exemple).

Crée un dossier avec les photos nommées « 001_lea-martin.jpg » et un tableau envois.csv (ouvrable dans Excel)
qui dit à quelle adresse envoyer chacune : on peut alors tout envoyer à la main, depuis n'importe quelle boîte mail.
"""
from __future__ import annotations

import csv
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .mail_queue import GUEST, PENDING, MailQueue
from .storage import slugify

log = logging.getLogger(__name__)

HEADER = ("Destinataire", "Prénom", "Nom", "Fichier photo", "État", "Dernière erreur", "Date de la photo")
README = """Envois de photos qui ne sont pas partis
=======================================

envois.csv (à ouvrir avec Excel) indique, pour chaque photo de ce dossier, l'adresse mail du destinataire.
Envoie chaque photo en pièce jointe à son destinataire avec ta messagerie habituelle.

Attention : le Photobooth continue d'essayer d'envoyer ces mêmes photos dès que la connexion revient. Si tu les envoies
toi-même, vide la file d'attente ou laisse-la partir : tes invités risquent sinon de recevoir leur photo deux fois.
"""


@dataclass(frozen=True)
class ExportResult:
    folder: Path
    exported: int     # photos copiées
    missing: int      # photos qui n'existent plus (listées dans le tableau, sans fichier)


def _safe(text: str) -> str:
    """Excel prend un texte qui commence par = + - @ pour une formule : on le neutralise (noms et erreurs seulement)."""
    return "'" + text if text and text[0] in "=+-@\t\r" else text


def _unique_folder(path: Path) -> Path:
    candidate, counter = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}-{counter}")
        counter += 1
    return candidate


def export_unsent(queue: MailQueue, exports_root: Path, now: datetime | None = None) -> ExportResult | None:
    """Exporte les envois destinés aux invités qui ne sont pas partis. None s'il n'y en a aucun."""
    items = queue.unsent_jobs(GUEST)
    if not items:
        return None
    now = now or datetime.now()
    folder = _unique_folder(exports_root / f"envois-{now:%Y%m%d-%H%M%S}")
    folder.mkdir(parents=True)
    rows, exported, missing = [], 0, 0
    for index, item in enumerate(items, start=1):
        job = item.job
        extension = ".gif" if job.photo_path.suffix.lower() == ".gif" else ".jpg"
        filename = f"{index:03d}_{slugify(job.guest_name) or 'invite'}{extension}"
        if job.photo_path.is_file():
            shutil.copy2(job.photo_path, folder / filename)
            exported += 1
            state = "en attente" if item.status == PENDING else "en échec"
        else:
            filename, state = "", "photo introuvable"
            missing += 1
        rows.append([_safe(job.recipient), _safe(job.guest_first_name), _safe(job.guest_last_name), filename, state,
                     _safe(item.last_error), datetime.fromtimestamp(item.created_at).strftime("%d/%m/%Y %H:%M")])
    with (folder / "envois.csv").open("w", encoding="utf-8-sig", newline="") as f:   # BOM : Excel lit bien les accents
        writer = csv.writer(f, delimiter=";")                                         # « ; » : séparateur d'Excel en France
        writer.writerow(HEADER)
        writer.writerows(rows)
    (folder / "LISEZMOI.txt").write_text(README, encoding="utf-8")
    log.info("Envois exportés : %d photo(s), %d introuvable(s) -> %s", exported, missing, folder)
    return ExportResult(folder, exported, missing)
