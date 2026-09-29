# SP Work Log

Work log for Pravin Shinde. Other contributors keep their own `<initials>_WorkLog.md`.

Every change gets an entry, newest first: `## YYYY-MM-DD — what changed`, a short
**Reason:** (why it was needed), **Changed:** (files touched), and anything done to
prod. Keep it brief — enough to answer "why is this like this?" months later.

---

## 2026-09-29 — Tracker: phase-less stages vanished when a project got a 2nd phase

**Reason:** On A1636 the Phase 1 Emulation timeline rendered blank after adding Phase 2.
Migration `0017` added the `Phase` model but never backfilled `Stage.phase`, so every
pre-existing stage sat at `NULL`. `Stage.save()` adopted stages into a lazily-created
Phase 1 only as they were saved — "Save All Automation" rescued the Automation stages,
the Emulation ones stayed `NULL`. Single-phase projects hid this (one unfiltered panel);
adding a phase switched `project_detail` to `s.phase_id == p.id` and the orphans matched
no phase and no Handover row, so they disappeared and became uneditable.

**Changed:**
- `tracker/models.py` — new `Project.ensure_phase_one()`; `add_phase()` calls it first, so
  splitting a legacy project can't strand stages. Also fixes `add_phase` numbering the new
  phase 1 and dropping `existing_zone_description` when the project had no `Phase` row.
- `tracker/views.py` — any remaining phase-less non-Handover stage groups with the first
  phase (panels and `phase_summaries`); `handover_stages` narrowed to Handover only.
- `tracker/migrations/0018_backfill_stage_phase.py` — data migration. **Not in git**
  (`.gitignore` has `*/migrations/`); lives only on the dev machine.

**Prod (`Auto-AD` @ 10.10.11.218, PG 17.4):** `pg_dump` custom-format backup taken and
`pg_restore --list`-verified first, plus a JSON snapshot of all 1,686 stage→phase rows.
Then `migrate tracker 0018`: orphans **1397 → 0** across 124 projects, phases 24 → 128
(104 created), 0 stages created/deleted, 0 pre-existing assignments moved, 126 Handover
stages still project-level. A1636 Phase 1 now `auto=6 emu=6`; its rollup corrected from
43% (Automation-only) to 29% across all 12.

**Verified:** single-phase pages render byte-identical before/after the backfill (A1485,
0 diff, same 26 queries) — the new Phase 1 rows are invisible because all phase UI is
gated on `>1` phase. Dashboard, reports, milestones, stage-projects and delay-owner all
200. Commit `876dd21`, pushed to `main`.

---

## 2026-09-28 — New `tools` app (ported from the standalone TextLists Flask app)

Brought the two utilities from `D:\Testing_All\TextLists` into AutoVerse as a new Django
app. That Flask app was unrunnable (`app.py:70` had `if __name__ = "__main__"`, a syntax
error) and its Excel writer used the positional `to_excel(writer, name)` signature that
pandas removed in 2.0.

### What was built

| Tool | URL | What it does |
|---|---|---|
| Hub | `/tools/` | Cards for each tool, from `tools/registry.py` |
| IO Text List Generator | `/tools/text-list/` | IO-list `.xlsx` → per-channel text lists for label/ferrule printing |
| SCL IO-Mapping Generator | `/tools/scl-io-mapping/` | Siemens TIA `POKE_BLK` mapping block |

Design decisions taken: **no models** (fully stateless), **no authentication**
(`/tools/` is matched by none of the per-software middleware), templates extend the
portal shell `templates/base.html`, and the text-list tool uses a **validate-then-download**
flow — the summary is shown first, then the browser re-posts the same file to stream the
workbook. No server-side state, no temp files.

### Legacy defects fixed in the port

1. `to_excel(writer, name)` positional → write with openpyxl directly.
2. Sheet names >31 chars or containing `[]:*?/\` → `safe_sheet_name()` sanitises,
   truncates and de-duplicates.
3. `word[0]` raised on blank/numeric `I/O Address` → counted and reported instead.
4. `Ferrules` used by formats 4/5 but never validated → fatal if absent, warns on blanks.
5. Sheets missing required columns were dropped in silence → each is listed with a reason.
6. `max(sheet['Channel '])` blew up on NaN/text → max taken from valid values only.
7. `if inputs:` / `if outputs:` truthiness bug — a keyed `defaultdict` is truthy, so an
   inputs-only file still produced a bogus all-channel OutputsList sheet.
8. `createSCL(5, QBytes, 10)` ignored `IBytes` and hardcoded DB 1/2/10 → all five values
   are real parameters.
9. Module-level mutable `output`/`data` globals (not thread-safe) → no module state.

### ARTPL IO-list template support

The project file `A1701-DHL-AUTO-IOL-T4-R2.xlsx` does not match the legacy shape, so the
parser now handles both:

- **Header row is scanned** over the first 10 rows — `CP01_IOM` has an "ARTPL / IO List"
  banner on row 1 and the real header on row 2.
- **`Channel` is blank** (all 64 `CP01_IOM` rows) or holds a port name (`XM`/`X4`/`X2` on
  `CP01_DRC`), so grouping falls back to **`IO Module Name`** (IO101–IO105, DRC1–DRC10).
  A numeric `Channel` still wins, so legacy files are unaffected.
- **`IO Module Name` is forward-filled** — it is written once per block and left blank on
  the 50 rows beneath.
- Rows are ordered by **`Pin`** when every pin is numeric, else file order (`Pin` is
  `LPM`/`RPM`/`LP4`… on the DRC sheets).
- **SPARE rows keep their placeholder address** (`Qxxxx`) so the printed strip lines up
  with the physical terminals; the count is surfaced as a warning.
- For module grouping, a module with no rows in a direction gets **no empty column** —
  `InputsList_CP01_IOM` carries only IO101/IO103, `OutputsList_CP01_IOM` only IO102/104/105.
  Numeric channels keep the full `min..max` range including gaps, as the legacy app did.

### Verification done

- `python manage.py check` — clean (only the pre-existing ckeditor warning).
- `python manage.py test tools` — **41 tests, all passing, 0.71s** (no DB; `SimpleTestCase`).
- **Legacy regression:** ran a synthetic IO list through both the original
  `script.py::createTexts` and the new `build_workbook` and diffed cell by cell —
  **all 5 formats byte-identical**.
- **SCL regression:** all 20 `dbNumber`/`count`/`byteOffset` operands match
  `createSCL(5,'10',10)` exactly.
- **Live HTTP round trip** with the real ARTPL file: anonymous GET 200 on all three
  pages; HTMX validate returns the partial only (no `<html>`); download streams the
  correct `.xlsx` with an `attachment` header; a stale fingerprint correctly refuses to
  download and re-renders the summary.
- Confirmed `/estimator/` and `/skillgap/` still redirect anonymous users (302).

### Files touched

New: `tools/` (`apps.py`, `registry.py`, `textlist.py`, `scl.py`, `exports.py`,
`forms.py`, `views.py`, `urls.py`, `tests.py`, `templates/tools/*.html`).

Edited:
- `IOLGenv2_BackEnd/settings.py` — `'tools'` in `INSTALLED_APPS`
- `IOLGenv2_BackEnd/urls.py` — `path('tools/', include('tools.urls'))`
- `IOLGenv2_BackEnd/access.py` — `'tools'` in `SOFTWARE` (defensive; nothing gates it)
- `templates/base.html` — sidebar entry (`bi-tools`), placed before Downloads
- `activitylog/middleware.py` — `/tools/` added to `SKIP_PREFIXES`

### Bug found in first browser use: Download dumped the .xlsx bytes into the page

The form had `hx-trigger="submit, change from:#id_text_format"`, so HTMX listened for
`submit` on the **form** and swallowed every submission — the Download button included.
The binary response was then swapped into `#textlist-summary` as text. `hx-disable` on
the Download button did nothing, because the listener was on the form, not the button.

Fix: the form's `action` is now the download URL and its `hx-trigger` lists only
`change from:#id_text_format`, so HTMX never hears a submit. The Validate button carries
its own `hx-post` (with a `formaction` fallback for no-JS), and the Download button is a
plain `type="submit"` that the browser sends natively as a file save. Guarded by
`ViewTests.test_form_never_lets_htmx_intercept_the_download`.

### Note on the activity log

Tools use is **deliberately not logged**. It is public and stateless — it stores nothing
and changes nothing, so an entry per generated text list would be noise. This is enforced
by the `/tools/` prefix in `activitylog/middleware.py::SKIP_PREFIXES` and guarded by
`ViewTests.test_tools_is_excluded_from_the_activity_log`.
