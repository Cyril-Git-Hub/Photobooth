"""Liste d'invités lue dans invites.xlsx : colonnes nom, prénom, mail (le mail peut être vide)."""
from __future__ import annotations

import logging
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

TEMPLATE_HEADERS = ("nom", "prénom", "mail")
MSG_HEADER = ("Je ne trouve pas les colonnes de {name}.\nLa première ligne doit contenir les titres : "
              "nom, prénom, mail.")
MSG_LOCKED = "{name} est ouvert dans Excel.\nFerme-le, puis reviens sur cet écran."
MSG_MISSING = "Fichier introuvable : {path}"
MSG_UNREADABLE = "Impossible de lire {name} : est-ce bien un fichier Excel (.xlsx) ?\n({error})"
MSG_NO_OPENPYXL = "openpyxl n'est pas installé.\nLance : pip install -r requirements.txt"

_HEADER_ALIASES = {
    "last_name": {"nom", "nomdefamille", "lastname", "famille", "name"},
    "first_name": {"prenom", "prenoms", "firstname", "givenname"},
    "email": {"mail", "email", "courriel", "adressemail", "adresseemail", "adresse", "emailaddress"},
}


class GuestListError(RuntimeError):
    """Liste illisible ; le message est destiné à être affiché à l'écran."""


@dataclass(frozen=True)
class Guest:
    last_name: str
    first_name: str
    email: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


def normalize_text(text: str) -> str:
    """Minuscules, sans accents ni ponctuation : « Jean-Éric » -> « jean eric »."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.casefold()).strip()


def _sort_key(guest: Guest) -> tuple[str, str]:
    return normalize_text(guest.first_name), normalize_text(guest.last_name)


def search_guests(guests: list[Guest], query: str) -> list[Guest]:
    """Invités dont le prénom ou le nom contient chaque mot recherché (sans accents ni majuscules, dans n'importe quel ordre)."""
    tokens = normalize_text(query).split()
    if not tokens:
        return list(guests)
    return [g for g in guests
            if all(token in normalize_text(f"{g.first_name} {g.last_name}") for token in tokens)]


def _cell_text(value) -> str:
    return "" if value is None else " ".join(str(value).split())


def _find_columns(header: list[str]) -> dict[str, int]:
    columns: dict[str, int] = {}
    for index, title in enumerate(header):
        key = normalize_text(title).replace(" ", "")
        for field, aliases in _HEADER_ALIASES.items():
            if key in aliases and field not in columns:
                columns[field] = index
    return columns


def load_guests(path: Path) -> list[Guest]:
    """Invités triés par prénom. Lève GuestListError (message affichable) si le fichier est inutilisable."""
    try:
        from openpyxl import load_workbook
        from openpyxl.utils.exceptions import InvalidFileException
    except ImportError as exc:
        raise GuestListError(MSG_NO_OPENPYXL) from exc

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except FileNotFoundError as exc:
        raise GuestListError(MSG_MISSING.format(path=path)) from exc
    except PermissionError as exc:
        raise GuestListError(MSG_LOCKED.format(name=path.name)) from exc
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise GuestListError(MSG_UNREADABLE.format(name=path.name, error=exc)) from exc
    try:
        sheet = workbook.active
        rows = [] if sheet is None else [[_cell_text(v) for v in row] for row in sheet.iter_rows(values_only=True)]
    except PermissionError as exc:
        raise GuestListError(MSG_LOCKED.format(name=path.name)) from exc
    finally:
        workbook.close()

    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    columns = _find_columns(rows[0])
    if "last_name" not in columns and "first_name" not in columns:
        raise GuestListError(MSG_HEADER.format(name=path.name))

    def cell(row: list[str], field: str) -> str:
        index = columns.get(field)
        return row[index] if index is not None and index < len(row) else ""

    guests = [Guest(cell(row, "last_name"), cell(row, "first_name"), cell(row, "email").lower())
              for row in rows[1:] if cell(row, "last_name") or cell(row, "first_name")]
    guests.sort(key=_sort_key)
    log.info("Liste d'invités chargée : %d invités, %d avec une adresse mail",
             len(guests), sum(1 for g in guests if g.email))
    return guests


def ensure_template(path: Path) -> bool:
    """Crée un invites.xlsx vide (titres de colonnes seulement) s'il n'existe pas. True si créé."""
    if path.exists():
        return False
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        return False
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Invités"
    sheet.append(list(TEMPLATE_HEADERS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for column, width in zip("ABC", (26, 26, 40)):
        sheet.column_dimensions[column].width = width
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    log.info("Liste d'invités vide créée : %s", path)
    return True
