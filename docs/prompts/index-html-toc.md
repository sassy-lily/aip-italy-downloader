# Feature prompt: generate `index.html` table of contents after download

**Goal.** After a version snapshot finishes downloading, write an `index.html`
into that version's directory (`AIP_OUTPUT_DIR/<version>/index.html`) that serves
as a human-friendly, browsable table of contents linking to the downloaded PDFs.

## Where it fits

- Add a new module `src/aip_downloader/index.py` whose public functions render a
  `VersionManifest` to an HTML string and write it to the version directory.
  Keep render and write **separable** so the render is testable without touching
  the filesystem — e.g. `render_index(manifest) -> str` and
  `write_index(manifest, version_dir) -> Path`.
- Wire it into `pipeline.run()` immediately after
  `manifest_io.save(manifest, version_dir)` (currently `pipeline.py:102`). It
  must run only on real downloads, never in `dry_run` (which already returns
  earlier in the function).

## What the page must contain

- A title/header showing the version: `version_id`, `effective_date`, and
  `airac_cycle` if present, plus a generated-at timestamp.
- Pages grouped by `AipSection` (GEN → ENR → AD), sections in `SECTION_RANK`
  order, and pages **within** each section kept in manifest order
  (`ordering_index` — already the authoritative menu order; do not re-sort
  numerically).
- For each page: its `ordering_index`, `page_id`, `title` (fall back to
  `page_id` when title is `None`), and a **relative** `<a href>` to its
  `output_filename` so the link works when the file is opened directly from the
  version directory.
- Reflect `PageStatus`: only link pages that are actually present locally
  (`DONE` / `SKIPPED`); show `FAILED` / `PENDING` pages as non-linked, visually
  marked rows so gaps are obvious. Optionally show `byte_size` as a
  human-readable size.
- A small summary line (counts per section and total, plus how many
  failed/missing).

## Implementation constraints (follow project conventions)

- Type hints on public functions; use `pathlib`; use the stdlib `logging`
  module (no `print`); log the written path at INFO.
- Pure stdlib only — **no new dependencies** (no Jinja). Build the HTML with
  `html.escape` for all dynamic text and simple f-strings / `str.join`.
  Self-contained file: inline a small `<style>` block, no external assets.
- Write the file atomically (the same `.part` → `replace` pattern used in
  `manifest.save`), UTF-8 encoded, with a proper `<!doctype html>` and
  `<meta charset>`.
- Keep network/parsing/storage concerns separate — `index.py` does rendering
  plus its own file write only; it must not import httpx or do any network I/O.

## Tests (`tests/`, pytest, no live site)

- Unit-test `render_index` against a hand-built `VersionManifest` fixture:
  assert sections appear in GEN/ENR/AD order, pages keep manifest order, hrefs
  equal `output_filename` and are relative, titles fall back to `page_id`, and
  `FAILED` / `PENDING` pages are rendered unlinked.
- Test that the output escapes HTML-special characters in titles.
- Test `write_index` writes to `<version_dir>/index.html` and returns that path
  (use `tmp_path`).

## Out of scope

- A top-level index across multiple versions (this is per-version only).
- Any styling beyond a minimal readable stylesheet.

## Verification

- `ruff format . && ruff check .` clean.
- `pytest` green.
- Opening a generated `index.html` in a browser yields a working clickable TOC.
