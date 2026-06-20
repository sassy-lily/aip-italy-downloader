# Task: make the version snapshot directory sort chronologically

## Problem
Each version snapshot is written to `AIP_OUTPUT_DIR/<dirname>/`, where `<dirname>`
is currently `naming.slugify_version(version_id)` — e.g. `A06-26-_2026_06_11`.
That name leads with the AIRAC code (`A<nn>-<yy>`), so it does NOT sort
chronologically across a year boundary: `A01-26-…` (Jan 2026) sorts *before*
`A12-25-…` (Dec 2025). The snapshots should sort in true chronological order in a
plain `ls`.

## Fix
Derive the directory name from the edition's **effective date** (ISO `YYYY-MM-DD`,
which sorts naturally) followed by the AIRAC code:

    2026-06-11_A06-26/      (was: A06-26-_2026_06_11/)
    2026-07-09_A07-26/

- Format: `f"{effective_date:%Y-%m-%d}_{airac_code}"`, where `airac_code` is the
  sanitized `VersionInfo.airac_cycle` (e.g. `A06-26`).
- If `airac_cycle` is `None`, fall back to the ISO date alone (still chronological).
- **Do NOT change `version_id`.** It is the change-detection key (`version.detect_change`)
  and is recorded in `manifest.json`; only the on-disk directory name changes.
- New downloads only — no migration/renaming of existing directories.

## Where
- `src/aip_downloader/naming.py`: add a pure helper, e.g.
  `version_dirname(effective_date: date, airac_cycle: str | None) -> str`,
  reusing the existing sanitization (`slugify_version`) for the code component.
  Keep `slugify_version` (still useful for the code part).
- `src/aip_downloader/pipeline.py`: replace
  `version_dir = settings.output_dir / naming.slugify_version(active.version_id)`
  with the new `naming.version_dirname(active.effective_date, active.airac_cycle)`.

## Tests
- `tests/test_naming.py`: add cases for `version_dirname` — normal case
  (`date(2026,6,11), "A06-26"` → `2026-06-11_A06-26`), the `None` fallback, and
  that chronological string sort matches date order across a year boundary
  (e.g. Dec 2025 sorts before Jan 2026).
- `tests/test_pipeline.py`: update the expected `version_dir` to the new scheme
  (the FakeVersionProvider returns effective_date `2026-06-25`, airac_cycle
  `2026-07` → dir `2026-06-25_2026-07`).

## Constraints & done-when
- Follow this repo's CLAUDE.md and my account-level working agreement; commit the
  change as one logical, conventional, attributed commit.
- `ruff format . && ruff check .` clean; `pytest` green.
- Optionally confirm live with `PYTHONPATH=src python -m aip_downloader --limit 1`:
  the new directory name appears and sorts chronologically; the manifest's
  `version_id` is unchanged.
