"""Turns an IO-list workbook into per-channel printable text lists.

No HTTP, no DB here -- mirrors the estimator's imports.py / exports.py split (pure logic
in, structured data out), so the parsing rules can be reasoned about (and tested)
independently of the view that calls them.

Ported from the standalone Flask app at TextLists/script.py, which this replaces. The
output layout is deliberately byte-compatible with what that app produced -- including
the 0-based index column in column A that pandas' `to_excel` wrote by default -- because
downstream label software may read these sheets by column position.

Two IO-list shapes are supported:

* the legacy one, whose sheets carry a numeric `Channel` column, giving one column of
  output per channel number; and
* the ARTPL template, where `Channel` is blank or holds a port name (XM/X4/X2), the
  header sits below a title banner, and the real grouping unit is `IO Module Name`
  (IO101..IO105, DRC1..DRC10) with `Pin` giving the position inside the module.

Which of the two applies is worked out per sheet -- see _grouping().

analyse() and build_workbook() share one private `_prepare()`, so the summary shown on
the review page and the workbook that is downloaded can never disagree.
"""
import hashlib
import re
from dataclasses import dataclass, field
from io import BytesIO

import pandas as pd
from openpyxl import Workbook

TAG_COLUMN = 'Tag'
ADDRESS_COLUMN = 'I/O Address'
CHANNEL_COLUMN = 'Channel'
MODULE_COLUMN = 'IO Module Name'
PIN_COLUMN = 'Pin'
FERRULES_COLUMN = 'Ferrules'

# Every sheet needs these two, plus at least one column to group by.
REQUIRED_COLUMNS = [TAG_COLUMN, ADDRESS_COLUMN]
GROUP_COLUMNS = [CHANNEL_COLUMN, MODULE_COLUMN]

# The ARTPL template puts a title banner ("ARTPL | IO List | Document No-...") above the
# real header row, so the header is not always row 1. Same approach as estimator/imports.py.
MAX_HEADER_SCAN_ROWS = 10

# The five output formats, numbered as the legacy app numbered them -- the numbers are
# part of the form's posted data, so they must not be renumbered.
FORMAT_IO_AND_TAG = 1
FORMAT_TAG = 2
FORMAT_IO = 3
FORMAT_FERRULES = 4
FORMAT_IO_AND_FERRULES = 5

FORMAT_CHOICES = [
    (FORMAT_IO_AND_TAG, 'IO Address + Tag'),
    (FORMAT_TAG, 'Only Tag'),
    (FORMAT_IO, 'Only IO Address'),
    (FORMAT_FERRULES, 'Only Ferrules'),
    (FORMAT_IO_AND_FERRULES, 'IO Address + Ferrules'),
]
FORMAT_LABELS = dict(FORMAT_CHOICES)
FORMATS_NEEDING_FERRULES = {FORMAT_FERRULES, FORMAT_IO_AND_FERRULES}

# A channel number far outside this range is a data-entry slip, not a real channel.
# The legacy `range(1, max(channel) + 1)` would happily try to build that many columns
# and hang the worker; we refuse it and name the offending row instead.
MAX_CHANNELS = 512

# Excel's own limits on a worksheet name.
MAX_SHEET_NAME = 31
ILLEGAL_SHEET_CHARS = r'[]:*?/\\'

# A real Siemens address. SPARE rows in the ARTPL template carry a placeholder such as
# "Qxxxx" instead -- kept (the printed strip has to line up with the physical terminals)
# but counted, so the summary can say how many there were.
REAL_ADDRESS = re.compile(r'^[IQ]\d+(\.\d+)?$', re.IGNORECASE)

# How many offending rows to quote back in a warning before saying "and N more".
MAX_EXAMPLES = 3


class TextListError(ValueError):
    """Raised when the upload can't be turned into text lists at all.

    The message is shown to the user as-is, so it must say what is wrong *and* what to
    do about it.
    """


# --------------------------------------------------------------------------- summaries

@dataclass(frozen=True)
class SkippedSheet:
    """A worksheet that was passed over, and why -- the legacy app dropped these
    silently, which is how people ended up with empty workbooks."""
    name: str
    reason: str


@dataclass(frozen=True)
class SheetSummary:
    name: str
    group_by: str = CHANNEL_COLUMN
    columns: list = field(default_factory=list)
    inputs_sheet_name: str = ''
    outputs_sheet_name: str = ''
    header_row: int = 1
    rows_read: int = 0
    blank_tag_rows: int = 0
    input_rows: int = 0
    output_rows: int = 0
    unusable_address_rows: int = 0
    unusable_channel_rows: int = 0
    placeholder_address_rows: int = 0
    min_channel: int = 0
    max_channel: int = 0
    empty_channels: list = field(default_factory=list)
    missing_ferrules_rows: int = 0
    warnings: list = field(default_factory=list)

    @property
    def column_summary(self):
        """Short description of the generated columns, for the review table."""
        if not self.columns:
            return '--'
        if self.group_by == CHANNEL_COLUMN:
            if self.min_channel == self.max_channel:
                return str(self.min_channel)
            return f'{self.min_channel}-{self.max_channel}'
        if len(self.columns) > 2:
            return f'{len(self.columns)}: {self.columns[0]} ... {self.columns[-1]}'
        return ', '.join(str(c) for c in self.columns)


@dataclass(frozen=True)
class WorkbookSummary:
    filename: str
    fingerprint: str
    text_format: int
    text_format_label: str
    sheets: list = field(default_factory=list)
    skipped_sheets: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def sheet_count(self):
        return len(self.sheets)

    @property
    def total_input_rows(self):
        return sum(s.input_rows for s in self.sheets)

    @property
    def total_output_rows(self):
        return sum(s.output_rows for s in self.sheets)


@dataclass
class _PreparedSheet:
    """A sheet's summary plus the column data itself. build_workbook() writes the data;
    analyse() throws it away and keeps only the summary."""
    summary: SheetSummary
    inputs: dict
    outputs: dict


# --------------------------------------------------------------------------- helpers

def _normalize_header(header):
    """Headers are matched loosely, so a file re-saved with the trailing space trimmed
    off "Channel " still works. The legacy app required the space verbatim."""
    return re.sub(r'\s+', ' ', str(header)).strip().lower()


def _blank(value):
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() in ('', 'nan')


def _clean(value):
    """Blank-safe string cleanup that also undoes pandas' float-ification of whole
    numbers (a channel or pin cell of 3 can come back as '3.0')."""
    if _blank(value):
        return ''
    text = str(value).strip()
    if text.endswith('.0') and text[:-2].lstrip('-').isdigit():
        return text[:-2]
    return text


def _direction(address):
    """'I' for an input address, 'Q' for an output, None for anything else.

    The legacy `word[0]` raised on a blank or numeric I/O Address; an unreadable address
    is now counted and reported rather than crashing the whole run.
    """
    first = _clean(address)[:1].upper()
    return first if first in ('I', 'Q') else None


def _channel(value):
    """Whole-number channel, or None. The legacy `max(sheet['Channel '])` blew up on a
    NaN or a text value anywhere in the column."""
    text = _clean(value)
    if not text:
        return None
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def safe_sheet_name(prefix, sheet, used):
    """An Excel-legal, unique worksheet name for `prefix` + `sheet`.

    Excel caps a name at 31 characters and rejects []:*?/\\ -- the legacy app passed the
    source sheet name straight through, so a long or punctuated name raised on save.
    Two long names can truncate to the same string, hence the `used` set and the ~2
    suffix.
    """
    cleaned = ''.join(' ' if ch in ILLEGAL_SHEET_CHARS else ch for ch in str(sheet)).strip()
    base = f'{prefix}_{cleaned}'.strip()[:MAX_SHEET_NAME] or prefix
    candidate, n = base, 1
    while candidate.lower() in used:
        n += 1
        suffix = f'~{n}'
        candidate = f'{base[:MAX_SHEET_NAME - len(suffix)]}{suffix}'
    used.add(candidate.lower())
    return candidate


def _format_cell(text_format, address, tag, ferrules):
    if text_format == FORMAT_IO_AND_TAG:
        return f'{address} {tag}'.strip()
    if text_format == FORMAT_TAG:
        return tag
    if text_format == FORMAT_IO:
        return address
    if text_format == FORMAT_FERRULES:
        return ferrules
    if text_format == FORMAT_IO_AND_FERRULES:
        return f'{address} {ferrules}'.strip()
    return tag


def _quote_rows(rows):
    shown = ', '.join(f'row {r}' for r in rows[:MAX_EXAMPLES])
    extra = len(rows) - MAX_EXAMPLES
    return f'{shown} and {extra} more' if extra > 0 else shown


def _read(uploaded_file):
    """Reads the upload once into memory and fingerprints it.

    Owning the bytes here means the file position is ours: pd.ExcelFile() reads to EOF,
    so a caller that handed us a live UploadedFile could not read it again afterwards.
    It also makes InMemoryUploadedFile and TemporaryUploadedFile behave identically.
    """
    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError, ValueError):
        pass
    raw = uploaded_file.read() or b''
    fingerprint = f'{len(raw)}:{hashlib.sha256(raw[:1024 * 1024]).hexdigest()[:32]}'
    return BytesIO(raw), (getattr(uploaded_file, 'name', '') or 'workbook.xlsx'), fingerprint


# --------------------------------------------------------------------------- header row

def _unique_columns(header):
    """Column labels that are safe to index by: blanks get a placeholder, repeats get a
    suffix. Without this, a duplicated header makes frame[col] return a DataFrame."""
    columns, seen = [], {}
    for position, value in enumerate(header):
        name = '' if _blank(value) else str(value).strip()
        key = name or f'__col{position}'
        if key in seen:
            seen[key] += 1
            key = f'{key}__{seen[key]}'
        else:
            seen[key] = 0
        columns.append(key)
    return columns


def _locate_header(raw):
    """Finds the header row, which is not always row 1 -- the ARTPL template puts a
    title banner above it. Returns (row position, columns) or (None, reason)."""
    limit = min(MAX_HEADER_SCAN_ROWS, len(raw.index))
    reason = f'no header row with {", ".join(REQUIRED_COLUMNS)} in the first {limit} row(s)'
    for position in range(limit):
        values = raw.iloc[position].tolist()
        found = {_normalize_header(v) for v in values}
        missing = [c for c in REQUIRED_COLUMNS if _normalize_header(c) not in found]
        groupable = any(_normalize_header(c) in found for c in GROUP_COLUMNS)
        if not missing and groupable:
            return position, _unique_columns(values)
        if not missing:
            reason = f'missing a {" or ".join(GROUP_COLUMNS)} column'
        elif len(missing) < len(REQUIRED_COLUMNS):
            reason = 'missing ' + ', '.join(missing)
    return None, reason


def _sheet_frame(workbook, sheet_name):
    """Returns (frame, lookup, header_row), or (None, reason, 0) when there is no
    header row to be found."""
    raw = workbook.parse(sheet_name, dtype=str, header=None)
    position, columns = _locate_header(raw)
    if position is None:
        return None, columns, 0  # `columns` carries the reason in this branch

    frame = raw.iloc[position + 1:].copy()
    frame.columns = columns
    frame = frame.dropna(how='all')
    lookup = {_normalize_header(c): c for c in columns}
    return frame, lookup, position + 1


def _grouping(frame, lookup):
    """Which column becomes one column of output. Prefers a numeric Channel (the legacy
    layout); falls back to IO Module Name when Channel is blank or holds a port name."""
    channel_column = lookup.get(_normalize_header(CHANNEL_COLUMN))
    if channel_column is not None:
        if any(_channel(v) is not None for v in frame[channel_column]):
            return CHANNEL_COLUMN, channel_column
    module_column = lookup.get(_normalize_header(MODULE_COLUMN))
    if module_column is not None:
        return MODULE_COLUMN, module_column
    return None, None


# --------------------------------------------------------------------------- parsing

def _prepare(data, text_format):
    """Returns (prepared_sheets, skipped_sheets). Raises TextListError when there is
    nothing usable to write."""
    try:
        workbook = pd.ExcelFile(data)
        sheet_names = list(workbook.sheet_names)
    except Exception as exc:  # noqa: BLE001 -- pandas/openpyxl raise a wide variety here
        raise TextListError(
            f"Couldn't read this file as an Excel workbook: {exc}. "
            'If it is password-protected, remove the password and try again.'
        ) from exc

    prepared, skipped, used_names = [], [], set()
    any_ferrules_column = False

    for sheet_name in sheet_names:
        try:
            frame, lookup, header_row = _sheet_frame(workbook, sheet_name)
        except Exception as exc:  # noqa: BLE001
            skipped.append(SkippedSheet(sheet_name, f'could not be read ({exc})'))
            continue
        if frame is None:
            skipped.append(SkippedSheet(sheet_name, lookup))  # lookup holds the reason
            continue

        group_by, group_column = _grouping(frame, lookup)
        if group_column is None:
            skipped.append(SkippedSheet(
                sheet_name, f'no usable {" or ".join(GROUP_COLUMNS)} values'))
            continue

        ferrules_column = lookup.get(_normalize_header(FERRULES_COLUMN))
        if ferrules_column:
            any_ferrules_column = True

        prepared.append(_prepare_sheet(
            sheet_name, frame, lookup, group_by, group_column, ferrules_column,
            text_format, used_names, header_row,
        ))

    if not prepared:
        detail = '; '.join(f'{s.name} -- {s.reason}' for s in skipped)
        raise TextListError(
            f'None of the {len(sheet_names)} worksheet(s) in this file has the columns '
            f'{", ".join(REQUIRED_COLUMNS)} plus a {" or ".join(GROUP_COLUMNS)} column. '
            + (f'({detail})' if detail else '')
        )

    if text_format in FORMATS_NEEDING_FERRULES and not any_ferrules_column:
        raise TextListError(
            f'The "{FORMAT_LABELS[text_format]}" format needs a "{FERRULES_COLUMN}" column, '
            'and none of the matching sheets has one. Pick another format or add the column.'
        )

    if not any(s.summary.input_rows or s.summary.output_rows for s in prepared):
        raise TextListError(
            f'No rows to write: no {ADDRESS_COLUMN} in this file starts with I or Q.'
        )

    return prepared, skipped


def _prepare_sheet(sheet_name, frame, lookup, group_by, group_column, ferrules_column,
                   text_format, used_names, header_row):
    tag_column = lookup[_normalize_header(TAG_COLUMN)]
    address_column = lookup[_normalize_header(ADDRESS_COLUMN)]
    pin_column = lookup.get(_normalize_header(PIN_COLUMN))
    by_channel = group_by == CHANNEL_COLUMN

    if not by_channel:
        # In the ARTPL template the module name is written once per block and left blank
        # on the rows beneath it, so carry it down before grouping.
        frame = frame.copy()
        frame[group_column] = frame[group_column].ffill()

    inputs, outputs = {}, {}
    order = []                       # group labels, in the order they first appear
    blank_tag_rows = 0
    bad_address_rows, bad_group_rows, placeholder_rows = [], [], []
    missing_ferrules_rows = 0
    rows_read = len(frame.index)
    pins_seen = []

    for index, row in frame.iterrows():
        row_number = index + 1       # raw index 0 is spreadsheet row 1

        tag = _clean(row[tag_column])
        if not tag:
            blank_tag_rows += 1      # the legacy dropna(subset=['Tag']), now counted
            continue

        address = _clean(row[address_column])
        direction = _direction(address)
        if direction is None:
            bad_address_rows.append(row_number)
            continue
        if not REAL_ADDRESS.match(address):
            placeholder_rows.append(row_number)

        if by_channel:
            label = _channel(row[group_column])
            if label is None:
                bad_group_rows.append(row_number)
                continue
            if label > MAX_CHANNELS:
                raise TextListError(
                    f'Sheet "{sheet_name}" has channel {label} on row {row_number} -- that '
                    f'would produce {label} columns. Fix the {CHANNEL_COLUMN} value and try again.'
                )
        else:
            label = _clean(row[group_column])
            if not label:
                bad_group_rows.append(row_number)
                continue

        if label not in order:
            order.append(label)

        ferrules = _clean(row[ferrules_column]) if ferrules_column else ''
        if text_format in FORMATS_NEEDING_FERRULES and not ferrules:
            missing_ferrules_rows += 1

        pin = _channel(row[pin_column]) if pin_column is not None else None
        pins_seen.append(pin)

        cell = _format_cell(text_format, address, tag, ferrules)
        bucket = inputs if direction == 'I' else outputs
        bucket.setdefault(label, []).append((pin, cell))

    # Order rows inside each group by Pin when every row has a numeric one; otherwise
    # keep the order they appear in the file (Pin is LPM/RPM/... on the DRC sheets).
    sort_by_pin = bool(pins_seen) and all(p is not None for p in pins_seen)
    for bucket in (inputs, outputs):
        for label, entries in bucket.items():
            if sort_by_pin:
                entries.sort(key=lambda entry: entry[0])
            bucket[label] = [text for _, text in entries]

    input_rows = sum(len(v) for v in inputs.values())
    output_rows = sum(len(v) for v in outputs.values())

    if by_channel:
        observed = sorted(set(inputs) | set(outputs))
        min_channel = observed[0] if observed else 0
        max_channel = observed[-1] if observed else 0
        columns = list(range(min_channel, max_channel + 1)) if observed else []
        empty_channels = [c for c in columns if c not in observed]
    else:
        columns = [label for label in order if label in inputs or label in outputs]
        min_channel = max_channel = 0
        empty_channels = []

    # Only name a sheet we will actually write. The legacy `if inputs:` / `if outputs:`
    # tested a defaultdict that any lookup had already keyed, so an inputs-only file
    # still got a full-width, entirely empty OutputsList sheet.
    inputs_name = safe_sheet_name('InputsList', sheet_name, used_names) if input_rows else ''
    outputs_name = safe_sheet_name('OutputsList', sheet_name, used_names) if output_rows else ''

    warnings = []
    if header_row > 1:
        warnings.append(f'Header row found on row {header_row}.')
    if not by_channel:
        warnings.append(
            f'Grouped by {MODULE_COLUMN} ({len(columns)} module(s)) -- the {CHANNEL_COLUMN} '
            'column is blank or not numeric on this sheet.'
        )
    if blank_tag_rows:
        warnings.append(f'{blank_tag_rows} row(s) skipped: the {TAG_COLUMN} cell is empty.')
    if bad_address_rows:
        warnings.append(
            f'{len(bad_address_rows)} row(s) skipped: the {ADDRESS_COLUMN} is blank or does not '
            f'start with I or Q ({_quote_rows(bad_address_rows)}).'
        )
    if bad_group_rows:
        warnings.append(
            f'{len(bad_group_rows)} row(s) skipped: no usable {group_by} value '
            f'({_quote_rows(bad_group_rows)}).'
        )
    if placeholder_rows:
        warnings.append(
            f'{len(placeholder_rows)} row(s) have a placeholder address such as "Qxxxx" '
            'rather than a real one. They are kept so the printed strip still lines up '
            'with the terminals.'
        )
    if empty_channels:
        warnings.append(
            f'Channels {min_channel}-{max_channel}; channel(s) '
            f'{", ".join(str(c) for c in empty_channels)} have no rows and will be written as '
            'empty columns.'
        )
    if by_channel and min_channel > 1:
        warnings.append(f'The lowest channel in this sheet is {min_channel}, not 1.')
    if missing_ferrules_rows:
        warnings.append(
            f'{missing_ferrules_rows} of {input_rows + output_rows} row(s) have no '
            f'{FERRULES_COLUMN} value -- those cells will be blank.'
        )
    if input_rows and not output_rows:
        warnings.append('Only inputs found -- no OutputsList sheet will be written.')
    if output_rows and not input_rows:
        warnings.append('Only outputs found -- no InputsList sheet will be written.')
    for written, prefix in ((inputs_name, 'InputsList'), (outputs_name, 'OutputsList')):
        if written and written != f'{prefix}_{sheet_name}':
            warnings.append(
                f'Sheet name shortened: "{prefix}_{sheet_name}" will be written as "{written}" '
                f'(Excel allows {MAX_SHEET_NAME} characters and no {ILLEGAL_SHEET_CHARS}).'
            )

    summary = SheetSummary(
        name=sheet_name,
        group_by=group_by,
        columns=columns,
        inputs_sheet_name=inputs_name,
        outputs_sheet_name=outputs_name,
        header_row=header_row,
        rows_read=rows_read,
        blank_tag_rows=blank_tag_rows,
        input_rows=input_rows,
        output_rows=output_rows,
        unusable_address_rows=len(bad_address_rows),
        unusable_channel_rows=len(bad_group_rows),
        placeholder_address_rows=len(placeholder_rows),
        min_channel=min_channel,
        max_channel=max_channel,
        empty_channels=empty_channels,
        missing_ferrules_rows=missing_ferrules_rows,
        warnings=warnings,
    )
    return _PreparedSheet(summary=summary, inputs=inputs, outputs=outputs)


def _summarise(prepared, skipped, filename, fingerprint, text_format):
    warnings = []
    if skipped:
        warnings.append(
            f'{len(skipped)} worksheet(s) skipped because they do not have the required columns.'
        )
    return WorkbookSummary(
        filename=filename,
        fingerprint=fingerprint,
        text_format=text_format,
        text_format_label=FORMAT_LABELS.get(text_format, ''),
        sheets=[p.summary for p in prepared],
        skipped_sheets=skipped,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- public API

def analyse(uploaded_file, text_format):
    """Validates the upload and reports what would be written, without building it."""
    data, filename, fingerprint = _read(uploaded_file)
    prepared, skipped = _prepare(data, text_format)
    return _summarise(prepared, skipped, filename, fingerprint, text_format)


def build_workbook(uploaded_file, text_format):
    """Returns (BytesIO of the .xlsx, WorkbookSummary)."""
    data, filename, fingerprint = _read(uploaded_file)
    prepared, skipped = _prepare(data, text_format)

    workbook = Workbook()
    workbook.remove(workbook.active)  # drop the default empty sheet
    for sheet in prepared:
        if sheet.summary.inputs_sheet_name:
            _write_sheet(workbook, sheet.summary.inputs_sheet_name, sheet.inputs, sheet.summary)
        if sheet.summary.outputs_sheet_name:
            _write_sheet(workbook, sheet.summary.outputs_sheet_name, sheet.outputs, sheet.summary)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer, _summarise(prepared, skipped, filename, fingerprint, text_format)


def _write_sheet(workbook, title, groups, summary):
    """One group per column, matching what pandas' to_excel() produced for the legacy
    app: A1 blank, the column labels along row 1 from B, and a 0-based row counter down
    column A."""
    worksheet = workbook.create_sheet(title)
    labels = summary.columns
    if summary.group_by != CHANNEL_COLUMN:
        # A module with only outputs would otherwise leave a blank column on the inputs
        # strip, and vice versa. Numeric channels keep the full min..max range, empties
        # included, because that is what the legacy app wrote.
        labels = [label for label in labels if groups.get(label)]
    depth = max((len(groups.get(label, ())) for label in labels), default=0)

    for offset, label in enumerate(labels):
        worksheet.cell(row=1, column=offset + 2, value=label)
    for index in range(depth):
        worksheet.cell(row=index + 2, column=1, value=index)
        for offset, label in enumerate(labels):
            values = groups.get(label, ())
            if index < len(values):
                worksheet.cell(row=index + 2, column=offset + 2, value=values[index])
    return worksheet
