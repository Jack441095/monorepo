"""Shared data helpers for Audio_Too agents (SQLite via Website/db.py)."""

from __future__ import annotations

import csv
import html
import inspect
import re
import zipfile
from datetime import datetime
from pathlib import Path

from Shared.activity_log import log_event


ROOT = Path(__file__).resolve().parent
BUSINESS_ROOT = ROOT.parent.parent
WEBSITE_ROOT = BUSINESS_ROOT / "app"
import sys

if str(WEBSITE_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBSITE_ROOT))

import db as sqlite_db  # noqa: E402

DATA = ROOT / "data"
EXPORTS = ROOT / "exports"

LOGGABLE_TABLES = {"clients", "projects", "leads", "invoices", "drafts", "campaigns", "followups", "sessions", "expenses"}


def actor_from_caller() -> str | None:
    for frame in inspect.stack()[2:10]:
        path = str(frame.filename).replace("\\", "/")
        if "/Admin/" in path or path.endswith("/Admin/local_agent.py"):
            return "admin"
        if "/Marketing/" in path or path.endswith("/Marketing/main.py"):
            return "marketing"
    return None


def record_label(name: str, record: dict) -> str:
    for field in ("lead", "client", "name", "project", "subject", "campaign", "id"):
        value = record.get(field)
        if value:
            return str(value)
    return name


def log_agent_record_event(action: str, name: str, record: dict) -> None:
    actor = actor_from_caller()
    if not actor or name not in LOGGABLE_TABLES:
        return
    log_event(f"{name}_{action}", record_label(name, record), actor=actor)


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "record"


def _ensure_db() -> None:
    sqlite_db.init_db()


def load_records(name: str) -> list[dict]:
    _ensure_db()
    if name not in sqlite_db.TABLES:
        raise KeyError(f"Unknown table: {name}")
    return sqlite_db.list_records(name)


def save_records(name: str, records: list[dict]) -> None:
    _ensure_db()
    sqlite_db.replace_records(name, records)


def add_record(name: str, record: dict) -> dict:
    _ensure_db()
    saved = sqlite_db.add_record(name, record)
    log_agent_record_event("created", name, saved)
    return saved


def list_records(name: str) -> list[dict]:
    return load_records(name)


def update_record(name: str, identifier: str, updates: dict, search_fields: list[str]) -> dict | None:
    _ensure_db()
    saved = sqlite_db.update_record(name, identifier, updates, search_fields)
    if saved:
        log_agent_record_event("updated", name, saved)
    return saved


def export_json_snapshots() -> list[Path]:
    _ensure_db()
    return sqlite_db.export_json_snapshots()


def format_table(records: list[dict], fields: list[str], empty_message: str) -> str:
    if not records:
        return empty_message

    lines = []
    for record in records:
        parts = [str(record.get(field, "") or "-") for field in fields]
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines)


def export_csv(name: str, fields: list[str], filename: str) -> Path:
    records = load_records(name)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    path = EXPORTS / filename
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})
    return path


def cell_ref(row: int, col: int) -> str:
    letters = ""
    while col:
        col, remainder = divmod(col - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def sheet_xml(records: list[dict], fields: list[str]) -> str:
    rows = [fields]
    rows.extend([[record.get(field, "") for field in fields] for record in records])
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            ref = cell_ref(row_index, col_index)
            if isinstance(value, int | float) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = html.escape("" if value is None else str(value))
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>'
        f'{"".join(xml_rows)}'
        '</sheetData>'
        '</worksheet>'
    )


def export_xlsx(name: str, fields: list[str], filename: str) -> Path:
    records = load_records(name)
    return export_multi_sheet_xlsx({name.title(): (fields, records)}, filename)


def export_multi_sheet_xlsx(sheets: dict[str, tuple[list[str], list[dict]]], filename: str) -> Path:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    path = EXPORTS / filename
    sheet_names = list(sheets)

    workbook_sheets = "".join(
        f'<sheet name="{html.escape(sheet_name[:31])}" sheetId="{index}" r:id="rId{index}"/>'
        for index, sheet_name in enumerate(sheet_names, start=1)
    )
    workbook_rels = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index, _ in enumerate(sheet_names, start=1)
    )
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index, _ in enumerate(sheet_names, start=1)
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f"{overrides}"
            "</Types>",
        )
        workbook.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        workbook.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{workbook_sheets}</sheets>"
            "</workbook>",
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{workbook_rels}"
            "</Relationships>",
        )
        for index, sheet_name in enumerate(sheet_names, start=1):
            fields, records = sheets[sheet_name]
            workbook.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml(records, fields))
    return path
