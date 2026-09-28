# SP ToDo

Task list for Pravin Shinde. Other contributors keep their own `<initials>_ToDo.md`.

---

## Open

### `tools` app

- [ ] **Try more real IO lists through the text-list tool.** Only the legacy shape and
      the ARTPL T4 template (`A1701-DHL-AUTO-IOL-T4-R2.xlsx`) have been exercised.
      Older revisions (T0–T3) may lay the header out differently — the scanner covers the
      first 10 rows, which is a guess, not a measurement.
- [ ] **Decide whether the printed strips look right on the label printer.** The module
      grouping (one column per IO module, rows in `Pin` order) is a design decision, not
      something the old tool did. Worth printing one strip before relying on it.
- [ ] **Delete or archive `D:\Testing_All\TextLists`** once the Django tool is confirmed
      in use. It is unrunnable as it stands and is now a duplicate.
- [ ] **Confirm the 15 MB upload cap is generous enough** (`TextListForm.MAX_UPLOAD_BYTES`).
      The ARTPL file is 34 KB, so there is a lot of headroom, but a large multi-panel
      list has not been tried. If the cap is ever raised, `web.config`'s
      `maxAllowedContentLength` needs checking too.
- [ ] **Consider a `Ferrules` column in the ARTPL template.** Formats 4 and 5 (the two
      ferrule formats) currently fail on it with a clear message, because the template has
      no such column.

### Nice to have

- [ ] Pin `pandas` in `requirements.txt`. It is unpinned; the port assumes ≥2.0 semantics.
- [ ] `BootstrapFormMixin` is now duplicated in `estimator/forms.py` and `tools/forms.py`.
      If a third app needs it, move it to a shared module rather than copying again.

## Done

- [x] Build the `tools` app with a hub page, the IO Text List Generator and the SCL
      IO-Mapping Generator — no models, no auth. *(2026-09-28)*
- [x] Fix the nine defects carried over from the legacy Flask app. *(2026-09-28)*
- [x] Support the ARTPL IO-list template (banner row, blank/text `Channel`, grouping by
      `IO Module Name`, forward-filled module names, `Pin` ordering, SPARE placeholders).
      *(2026-09-28)*
- [x] Prove the port matches the legacy output — 5/5 formats byte-identical, all 20 SCL
      operands identical. *(2026-09-28)*
- [x] Exclude `/tools/` from the activity log. *(2026-09-28)*
- [x] 41 tests, all passing, no database. *(2026-09-28)*
