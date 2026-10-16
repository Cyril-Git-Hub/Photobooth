"""Liste d'invités (.xlsx, .xls ou .ods) : colonnes nom, prénom, mail."""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

TEMPLATE_HEADERS = ("nom", "prénom", "mail")
MSG_HEADER = ("Je ne trouve pas les colonnes de {name}.\nLa première ligne doit contenir les titres : "
              "nom, prénom, mail.")
MSG_LOCKED = "{name} est ouvert dans un tableur.\nFerme-le, puis reviens sur cet écran."
MSG_MISSING = "Fichier introuvable : {path}"
MSG_UNREADABLE = "Impossible de lire {name} : vérifie que le fichier Excel/OpenDocument est valide et non protégé.\n({error})"
MSG_UNSUPPORTED = "Format non pris en charge pour {name}. Utilise un fichier .xlsx, .xls ou .ods."
MSG_MISSING_LIBRARY = "La bibliothèque {library} est nécessaire pour lire {extension}.\nLance : pip install -r requirements.txt"
MAX_ODS_ROWS = 10_000
MAX_ODS_COLUMNS = 256

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


def _read_xlsx(path: Path) -> list[list[str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise GuestListError(MSG_MISSING_LIBRARY.format(library="openpyxl", extension=".xlsx")) from exc
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        return [] if sheet is None else [[_cell_text(v) for v in row] for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _read_xls(path: Path) -> list[list[str]]:
    try:
        import xlrd
    except ImportError as exc:
        raise GuestListError(MSG_MISSING_LIBRARY.format(library="xlrd", extension=".xls")) from exc
    workbook = xlrd.open_workbook(str(path), on_demand=True)
    try:
        if not workbook.nsheets:
            return []
        sheet = workbook.sheet_by_index(0)
        return [[_cell_text(sheet.cell_value(row, col)) for col in range(sheet.ncols)]
                for row in range(sheet.nrows)]
    finally:
        workbook.release_resources()


def _read_ods(path: Path) -> list[list[str]]:
    try:
        from odf.opendocument import load
        from odf.table import Table, TableCell, TableRow, CoveredTableCell
        from odf.teletype import extractText
    except ImportError as exc:
        raise GuestListError(MSG_MISSING_LIBRARY.format(library="odfpy", extension=".ods")) from exc

    document = load(str(path))
    tables = document.spreadsheet.getElementsByType(Table)
    if not tables:
        return []
    cell_names = {TableCell().qname, CoveredTableCell().qname}

    rows: list[list[str]] = []
    for row_element in tables[0].getElementsByType(TableRow):
        row: list[str] = []
        for cell in row_element.childNodes:
            if getattr(cell, "qname", None) not in cell_names:
                continue
            value = _cell_text(extractText(cell))
            if not value:
                value = _cell_text(cell.getAttribute("stringvalue") or cell.getAttribute("value")
                                   or cell.getAttribute("datevalue") or cell.getAttribute("booleanvalue"))
            try:
                repeat = int(cell.getAttribute("numbercolumnsrepeated") or 1)
            except (TypeError, ValueError):
                repeat = 1
            repeat = max(1, min(repeat, MAX_ODS_COLUMNS - len(row)))
            row.extend([value] * repeat)
            if len(row) >= MAX_ODS_COLUMNS:
                break
        while row and not row[-1]:
            row.pop()
        if not any(row):
            continue
        try:
            repeated_rows = int(row_element.getAttribute("numberrowsrepeated") or 1)
        except (TypeError, ValueError):
            repeated_rows = 1
        rows.extend([row] * max(1, min(repeated_rows, MAX_ODS_ROWS - len(rows))))
        if len(rows) >= MAX_ODS_ROWS:
            break
    return rows


def _guests_from_rows(path: Path, rows: list[list[str]]) -> list[Guest]:
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


def load_guests(path: Path) -> list[Guest]:
    """Lit .xlsx, .xls ou .ods. Les invités sont triés par prénom."""
    extension = path.suffix.casefold()
    readers = {".xlsx": _read_xlsx, ".xls": _read_xls, ".ods": _read_ods}
    reader = readers.get(extension)
    if reader is None:
        raise GuestListError(MSG_UNSUPPORTED.format(name=path.name))

    try:
        rows = reader(path)
    except FileNotFoundError as exc:
        raise GuestListError(MSG_MISSING.format(path=path)) from exc
    except PermissionError as exc:
        raise GuestListError(MSG_LOCKED.format(name=path.name)) from exc
    except GuestListError:
        raise
    except Exception as exc:
        raise GuestListError(MSG_UNREADABLE.format(name=path.name, error=exc)) from exc
    return _guests_from_rows(path, rows)


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
