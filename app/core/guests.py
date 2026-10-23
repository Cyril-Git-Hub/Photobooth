"""Liste d'invités (.xlsx, .xls ou .ods) : colonnes nom, prénom, pseudo, mail."""
from __future__ import annotations

import logging
import os
import re
import tempfile
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

TEMPLATE_HEADERS = ("nom", "prénom", "pseudo", "mail", "sexe")
MSG_HEADER = ("Je ne trouve pas les colonnes de {name}.\nLa première ligne doit contenir des titres reconnus : "
              "nom, prénom, pseudo ou mail.")
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
    "pseudo": {"pseudo", "surnom", "nickname", "alias"},
    "email": {"mail", "email", "courriel", "adressemail", "adresseemail", "adresse", "emailaddress"},
    "sex": {"sexe", "sex", "gender"},
}


class GuestListError(RuntimeError):
    """Liste illisible ; le message est destiné à être affiché à l'écran."""


@dataclass(frozen=True)
class Guest:
    last_name: str
    first_name: str
    email: str = ""
    pseudo: str = ""
    sex: str = ""

    @property
    def display_name(self) -> str:
        return self.pseudo or f"{self.first_name} {self.last_name}".strip()


def normalize_text(text: str) -> str:
    """Minuscules, sans accents ni ponctuation : « Jean-Éric » -> « jean eric »."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.casefold()).strip()


def _sort_key(guest: Guest) -> tuple[str, str, str]:
    return (normalize_text(guest.display_name), normalize_text(guest.first_name),
            normalize_text(guest.last_name))


def search_guests(guests: list[Guest], query: str) -> list[Guest]:
    """Invités dont le prénom ou le nom contient chaque mot recherché (sans accents ni majuscules, dans n'importe quel ordre)."""
    tokens = normalize_text(query).split()
    if not tokens:
        return list(guests)
    return [g for g in guests
            if all(token in normalize_text(f"{g.pseudo} {g.first_name} {g.last_name}") for token in tokens)]


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
    if "last_name" not in columns and "first_name" not in columns and "pseudo" not in columns:
        raise GuestListError(MSG_HEADER.format(name=path.name))

    def cell(row: list[str], field: str) -> str:
        index = columns.get(field)
        return row[index] if index is not None and index < len(row) else ""

    guests = [Guest(cell(row, "last_name"), cell(row, "first_name"),
                    cell(row, "email").lower(), cell(row, "pseudo"),
                    cell(row, "sex").strip().upper())
              for row in rows[1:] if cell(row, "last_name") or cell(row, "first_name") or cell(row, "pseudo")]
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


def validate_pseudos(path: Path, people: list[Guest]) -> None:
    """Verifie les pseudos requis et uniques avant de lancer la borne."""
    missing = sum(1 for guest in people if not guest.pseudo.strip())
    if missing:
        raise GuestListError(f"Pseudo obligatoire : {missing} invit\u00e9(s) sans pseudo dans {path.name}. "
                             "Complete la colonne 'pseudo'.")
    by_pseudo: dict[str, list[str]] = {}
    for guest in people:
        by_pseudo.setdefault(normalize_text(guest.pseudo), []).append(guest.pseudo)
    duplicates = [values[0] for values in by_pseudo.values() if len(values) > 1]
    if duplicates:
        raise GuestListError(f"Pseudo en double dans {path.name} : {', '.join(duplicates[:5])}. "
                             "Chaque invite doit avoir un pseudo unique.")


def update_guest_emails(path: Path, updates: dict[str, str]) -> None:
    """Met à jour les mails par pseudo dans un XLSX/ODS, sans réécrire les autres données."""
    if not updates:
        return
    by_pseudo = {normalize_text(pseudo): (pseudo, email.strip().lower())
                 for pseudo, email in updates.items()}
    if "" in by_pseudo:
        raise GuestListError("Impossible d'enregistrer l'adresse : le pseudo de l'invité est vide.")

    extension = path.suffix.casefold()
    if extension == ".xlsx":
        _update_xlsx_emails(path, by_pseudo)
    elif extension == ".ods":
        _update_ods_emails(path, by_pseudo)
    elif extension == ".xls":
        raise GuestListError("La modification des fichiers .xls n'est pas prise en charge. "
                             "Enregistre la liste au format .xlsx ou .ods pour modifier les mails.")
    else:
        raise GuestListError(MSG_UNSUPPORTED.format(name=path.name))


def _atomic_save(path: Path, save) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.stem}_", suffix=path.suffix,
                                         dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        save(temporary_path)
        os.replace(temporary_path, path)
    except PermissionError as exc:
        raise GuestListError(MSG_LOCKED.format(name=path.name)) from exc
    except OSError as exc:
        raise GuestListError(MSG_UNREADABLE.format(name=path.name, error=exc)) from exc
    except Exception as exc:
        raise GuestListError(MSG_UNREADABLE.format(name=path.name, error=exc)) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                log.warning("Fichier temporaire non supprimé : %s", temporary_path)


def _update_xlsx_emails(path: Path, updates: dict[str, tuple[str, str]]) -> None:
    try:
        from openpyxl import load_workbook
        workbook = load_workbook(path)
    except PermissionError as exc:
        raise GuestListError(MSG_LOCKED.format(name=path.name)) from exc
    except Exception as exc:
        raise GuestListError(MSG_UNREADABLE.format(name=path.name, error=exc)) from exc

    try:
        sheet = workbook.active
        header = [_cell_text(cell.value) for cell in sheet[1]]
        columns = _find_columns(header)
        pseudo_col = columns.get("pseudo")
        if pseudo_col is None:
            raise GuestListError(MSG_HEADER.format(name=path.name))
        email_col = columns.get("email")
        if email_col is None:
            email_col = len(header)
            sheet.cell(1, email_col + 1, "mail")

        found: dict[str, list[int]] = {key: [] for key in updates}
        for row in range(2, sheet.max_row + 1):
            pseudo = normalize_text(_cell_text(sheet.cell(row, pseudo_col + 1).value))
            if pseudo in found:
                found[pseudo].append(row)
        _require_unique_targets(found, updates, path)
        for pseudo, (_, email) in updates.items():
            sheet.cell(found[pseudo][0], email_col + 1, email)
        _atomic_save(path, workbook.save)
    finally:
        workbook.close()


def _row_cells(row, table_cell_names: set[str]) -> list[tuple[object, int, int]]:
    """Cellules physiques et plages de colonnes représentées par les répétitions ODS."""
    cells: list[tuple[object, int, int]] = []
    column = 0
    for child in row.childNodes:
        if getattr(child, "qname", None) not in table_cell_names:
            continue
        try:
            repeat = max(1, int(child.getAttribute("numbercolumnsrepeated") or 1))
        except (TypeError, ValueError):
            repeat = 1
        cells.append((child, column, repeat))
        column += repeat
    return cells


def _ods_cell_text(cell, extract_text) -> str:
    value = _cell_text(extract_text(cell))
    if not value:
        value = _cell_text(cell.getAttribute("stringvalue") or cell.getAttribute("value")
                           or cell.getAttribute("datevalue") or cell.getAttribute("booleanvalue"))
    return value


def _set_ods_cell(row, column: int, value: str, cell_names: set[str], table_cell_type) -> None:
    cells = _row_cells(row, cell_names)
    target = next(((cell, start, repeat) for cell, start, repeat in cells
                   if start <= column < start + repeat), None)
    if target is None:
        while sum(repeat for _, _, repeat in cells) <= column:
            cell = table_cell_type(valuetype="string")
            row.addElement(cell)
            cells.append((cell, sum(repeat for _, _, repeat in cells), 1))
        target = next((entry for entry in cells if entry[1] <= column < entry[1] + entry[2]), None)
    if target is None:
        raise GuestListError("Impossible de modifier la cellule mail dans le fichier ODS.")

    cell, start, repeat = target
    offset = column - start
    if repeat > 1:
        replacement: list[object] = []
        if offset:
            before = deepcopy(cell)
            before.setAttribute("numbercolumnsrepeated", str(offset))
            replacement.append(before)
        selected = deepcopy(cell)
        selected.removeAttribute("numbercolumnsrepeated")
        replacement.append(selected)
        after_count = repeat - offset - 1
        if after_count:
            after = deepcopy(cell)
            after.setAttribute("numbercolumnsrepeated", str(after_count))
            replacement.append(after)
        for part in replacement:
            row.insertBefore(part, cell)
        row.removeChild(cell)
        cell = selected

    for child in list(cell.childNodes):
        cell.removeChild(child)
    for name in ("value", "datevalue", "booleanvalue"):
        if cell.getAttribute(name) is not None:
            cell.removeAttribute(name)
    cell.setAttribute("valuetype", "string")
    if value:
        from odf.text import P
        cell.addElement(P(text=value))


def _update_ods_emails(path: Path, updates: dict[str, tuple[str, str]]) -> None:
    try:
        from odf.opendocument import load
        from odf.table import CoveredTableCell, Table, TableCell, TableRow
        from odf.teletype import extractText
    except ImportError as exc:
        raise GuestListError(MSG_MISSING_LIBRARY.format(library="odfpy", extension=".ods")) from exc
    try:
        document = load(str(path))
    except PermissionError as exc:
        raise GuestListError(MSG_LOCKED.format(name=path.name)) from exc
    except Exception as exc:
        raise GuestListError(MSG_UNREADABLE.format(name=path.name, error=exc)) from exc

    tables = document.spreadsheet.getElementsByType(Table)
    if not tables:
        raise GuestListError(MSG_HEADER.format(name=path.name))
    rows = tables[0].getElementsByType(TableRow)
    cell_names = {TableCell().qname, CoveredTableCell().qname}
    header_index = next((index for index, row in enumerate(rows)
                         if any(_ods_cell_text(cell, extractText)
                                for cell, _, _ in _row_cells(row, cell_names))), None)
    if header_index is None:
        raise GuestListError(MSG_HEADER.format(name=path.name))
    header_cells = _row_cells(rows[header_index], cell_names)
    header: list[str] = []
    for cell, _, repeat in header_cells:
        header.extend([_ods_cell_text(cell, extractText)] * repeat)
    columns = _find_columns(header)
    pseudo_col = columns.get("pseudo")
    if pseudo_col is None:
        raise GuestListError(MSG_HEADER.format(name=path.name))
    email_col = columns.get("email")
    if email_col is None:
        email_col = len(header)
        _set_ods_cell(rows[header_index], email_col, "mail", cell_names, TableCell)

    found: dict[str, list[object]] = {key: [] for key in updates}
    for row_index, row in enumerate(rows):
        if row_index == header_index:
            continue
        values: list[str] = []
        for cell, _, repeat in _row_cells(row, cell_names):
            values.extend([_ods_cell_text(cell, extractText)] * repeat)
        pseudo = normalize_text(values[pseudo_col] if pseudo_col < len(values) else "")
        if pseudo in found:
            try:
                row_repeats = max(1, int(row.getAttribute("numberrowsrepeated") or 1))
            except (TypeError, ValueError):
                row_repeats = 1
            found[pseudo].extend([row] * row_repeats)
    _require_unique_targets(found, updates, path)
    for pseudo, (_, email) in updates.items():
        _set_ods_cell(found[pseudo][0], email_col, email, cell_names, TableCell)

    _atomic_save(path, document.save)


def _require_unique_targets(found: dict[str, list], updates: dict[str, tuple[str, str]], path: Path) -> None:
    for pseudo, (display_pseudo, _) in updates.items():
        rows = found.get(pseudo, [])
        if len(rows) != 1:
            raise GuestListError(
                f"Impossible d'identifier de façon unique le pseudo « {display_pseudo} » dans {path.name}. "
                "Vérifie que les pseudos sont présents et uniques."
            )


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
    for column, width in zip("ABCDE", (26, 26, 32, 40, 14)):
        sheet.column_dimensions[column].width = width
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    log.info("Liste d'invités vide créée : %s", path)
    return True
