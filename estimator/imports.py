"""Parses an uploaded module-list spreadsheet into plain dict rows for the import
wizard's review step. No HTTP, no DB writes here -- mirrors the calculations.py /
exports.py split (pure logic in, structured data out), so the parsing rules can be
reasoned about (and tested) independently of the view that calls them.

Of the ~30-column BOM sheet, the estimator uses Line/Zone, Module Name, and a module
count (primarily "No. of DC roller/AC motor", falling back to "Quantity" when that's
blank/zero) to drive the effort calculation, plus Sr., Module No. and Floor Level kept
purely for reference on the review page. Every other column is read and discarded.
"""
import re

import pandas as pd

ZONE_COLUMN = 'Line/Zone'
MODULE_NAME_COLUMN = 'Module Name'
COUNT_PRIMARY_COLUMN = 'No. of DC roller/AC motor'
COUNT_FALLBACK_COLUMN = 'Quantity'
SR_COLUMN = 'Sr.'
MODULE_NO_COLUMN = 'Module No.'
FLOOR_LEVEL_COLUMN = 'Floor Level'

REQUIRED_COLUMNS = [ZONE_COLUMN, MODULE_NAME_COLUMN]

# Real-world exports often have a title row (or a couple of them) above the actual
# column headers -- e.g. a merged "Module List" banner row. Rather than assuming the
# header is always row 1, scan down a bit for the row that actually contains it.
MAX_HEADER_SCAN_ROWS = 10


class ModuleListParseError(ValueError):
    """Raised when the uploaded file can't be read, or is missing a required column."""


def _normalize_header(header):
    return re.sub(r'\s+', ' ', str(header)).strip().lower()


def _blank(value):
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() in ('', 'nan')


def _clean_text(value):
    """Blank-safe string cleanup that also undoes pandas' float-ification of whole
    numbers (a Sr./Module No. cell like 12 can come back as '12.0' once the column is
    forced to dtype=str)."""
    if _blank(value):
        return ''
    text = str(value).strip()
    if text.endswith('.0') and text[:-2].lstrip('-').isdigit():
        return text[:-2]
    return text


def parse_module_list(uploaded_file):
    """Reads an uploaded .xlsx/.xls/.csv module list and returns a list of dicts:
    {'row_number', 'sr', 'raw_module_name', 'module_no', 'floor_level', 'zone',
    'count'} -- one per non-blank row.

    `row_number` is the row's 1-based position in the sheet, for the user's own
    reference on the review page. `sr`/`module_no`/`floor_level` are blank when the
    sheet doesn't have those columns at all.
    """
    filename = (getattr(uploaded_file, 'name', '') or '').lower()
    try:
        if filename.endswith('.csv'):
            candidates = [pd.read_csv(uploaded_file, dtype=str, header=None)]
        else:
            # A workbook may have several sheets (e.g. a "Project Specifications" cover
            # sheet plus the actual module list on another) -- the real data isn't
            # necessarily on the first one, so every sheet is a candidate.
            sheets = pd.read_excel(uploaded_file, dtype=str, header=None, sheet_name=None)
            candidates = list(sheets.values())
    except Exception as exc:
        raise ModuleListParseError(f"Couldn't read this file as a module list: {exc}") from exc

    raw = header_row_index = None
    for sheet_df in candidates:
        found = _find_header_row(sheet_df)
        if found is not None:
            raw, header_row_index = sheet_df, found
            break

    if header_row_index is None:
        raise ModuleListParseError(f"Missing required column(s): {', '.join(REQUIRED_COLUMNS)}.")

    df = raw.iloc[header_row_index + 1:].reset_index(drop=True)
    df.columns = ['' if _blank(c) else str(c).strip() for c in raw.iloc[header_row_index]]

    header_by_normalized = {_normalize_header(c): c for c in df.columns}
    zone_col = header_by_normalized[_normalize_header(ZONE_COLUMN)]
    module_name_col = header_by_normalized[_normalize_header(MODULE_NAME_COLUMN)]
    count_primary_col = header_by_normalized.get(_normalize_header(COUNT_PRIMARY_COLUMN))
    count_fallback_col = header_by_normalized.get(_normalize_header(COUNT_FALLBACK_COLUMN))
    sr_col = header_by_normalized.get(_normalize_header(SR_COLUMN))
    module_no_col = header_by_normalized.get(_normalize_header(MODULE_NO_COLUMN))
    floor_level_col = header_by_normalized.get(_normalize_header(FLOOR_LEVEL_COLUMN))

    rows = []
    for i, sheet_row in df.iterrows():
        module_name = '' if _blank(sheet_row.get(module_name_col)) else str(sheet_row[module_name_col]).strip()
        if not module_name:
            continue  # blank filler row -- typical trailing rows in exported sheets

        zone = '' if _blank(sheet_row.get(zone_col)) else str(sheet_row[zone_col]).strip()
        count = _parse_count(sheet_row, count_primary_col, count_fallback_col)

        rows.append({
            # header_row_index and i are both 0-based positions within `raw`/`df`; +2
            # accounts for the header row itself plus converting to a 1-based row number.
            'row_number': header_row_index + i + 2,
            'sr': _clean_text(sheet_row.get(sr_col)) if sr_col else '',
            'raw_module_name': module_name,
            'module_no': _clean_text(sheet_row.get(module_no_col)) if module_no_col else '',
            'floor_level': _clean_text(sheet_row.get(floor_level_col)) if floor_level_col else '',
            'zone': zone,
            'count': count,
        })

    return rows


def _find_header_row(raw):
    """Returns the 0-based index of the first row (within the first
    MAX_HEADER_SCAN_ROWS) whose cells include both required column labels, or None if
    no such row is found."""
    required_normalized = {_normalize_header(c) for c in REQUIRED_COLUMNS}
    for row_index in range(min(MAX_HEADER_SCAN_ROWS, len(raw))):
        cell_values = {_normalize_header(v) for v in raw.iloc[row_index] if not _blank(v)}
        if required_normalized.issubset(cell_values):
            return row_index
    return None


def _parse_count(sheet_row, primary_col, fallback_col):
    for col in (primary_col, fallback_col):
        if not col or _blank(sheet_row.get(col)):
            continue
        try:
            value = int(float(str(sheet_row[col]).strip()))
        except ValueError:
            continue
        if value > 0:
            return value
    return 0


def normalize_name(raw_name):
    return raw_name.strip().lower()


def match_module_type(raw_name, module_types, aliases=None):
    """ModuleType for a raw sheet name: an exact case-insensitive match against the
    standard module type list, or -- failing that -- a previously-confirmed alias
    saved from an earlier import's review step (`aliases`: {normalized raw name:
    ModuleType}). Never fuzzy-guesses: a name that isn't an exact match and has no
    saved alias is left unmatched (None) for the user to pick explicitly, since a wrong
    silent guess is worse than one extra click."""
    key = normalize_name(raw_name)
    by_lower_name = {normalize_name(mt.name): mt for mt in module_types}

    exact = by_lower_name.get(key)
    if exact:
        return exact

    if aliases:
        return aliases.get(key)

    return None
