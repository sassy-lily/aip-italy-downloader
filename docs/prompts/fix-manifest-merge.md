# Task: make manifest writes merge, never overwrite (limit-safe)

## Problem
The per-version `manifest.json` is the sole source of truth for skip/resume and
conditional-GET delta detection: `pipeline.run` builds `prior_by_id` from it
(`pipeline.py:89-91`), and `download.download_page` only sends `If-None-Match` /
`If-Modified-Since` — or skips outright — when a matching prior page record
exists. Files on disk are never consulted directly.

But the manifest is written by **wholesale replacement**. At `pipeline.py:93`,
`manifest.pages = await download_all(..., ordered, ...)` is set to **only the
pages processed this run**, then `manifest_io.save` overwrites the file
(`manifest.py:106-113`). When `--limit N` is used, `ordered` is sliced to the
first `N` pages (`pipeline.py:70-72`), so the save **truncates** the manifest to
those `N` pages. A later full run then sees no prior record for the other pages,
sends no conditional headers, and re-downloads everything with full `200`
bodies — even though the PDFs are already on disk and the server would have
returned `304`.

(Confirmed in the current tree: 907 PDFs on disk, manifest lists 3 pages, after
a `--limit 3` run.)

## Fix
Make every manifest write **merge into** the existing manifest rather than
replace it — identically whether or not `--limit` was passed:

- Keyed by `page_id`: a page processed this run **updates** (replaces) its prior
  record; a page new this run is **appended**; a prior page **not** touched this
  run is **preserved unchanged** (keeping its status / hash / validators).
- The merged page list is ordered by `ordering_index` so the manifest stays in
  authoritative menu order.
- **No removal.** A version snapshot is append/update-only: pages don't leave an
  edition mid-cycle, and a genuinely different edition lands in its own
  `version_dir`, so stale-page pruning is out of scope here.
- `--dry-run` keeps its current behaviour: it returns before any save
  (`pipeline.py:85-87`), so it never writes a manifest. Leave that path intact.

This makes a limited run a safe, incremental top-up of the snapshot instead of a
destructive truncation, and a full run still updates every page in place.

## Where
- `src/aip_downloader/manifest.py`: add a pure helper (no I/O), e.g.

      def merge_pages(
          prior: VersionManifest | None, fresh: list[PageRecord]
      ) -> list[PageRecord]:

  Start from the prior pages (or empty), overlay `fresh` by `page_id`, append
  fresh-only ids, return sorted by `ordering_index`. Keep it next to the other
  manifest-shape logic; it must not import httpx or touch the filesystem.
- `src/aip_downloader/pipeline.py`: replace
  `manifest.pages = await download_all(...)` with code that captures the run's
  results and then sets `manifest.pages = manifest_io.merge_pages(existing,
  results)` before `manifest_io.save`. `existing` is already loaded at
  `pipeline.py:65`.

## Tests
- `tests/test_manifest.py`: unit-test `merge_pages` —
  - prior `[A, B, C]`, fresh `[B']` (updated) → `[A, B', C]`, B's new data wins,
    A and C untouched, order preserved;
  - fresh introduces a new id `D` → appended and sorted by `ordering_index`;
  - `prior=None` → returns `fresh` as-is.
- `tests/test_pipeline.py`: a run with `limit` set so only a subset is processed
  must **keep the untouched prior pages** in the saved manifest (with their prior
  status/etag intact) plus the freshly processed pages updated — i.e. assert the
  saved manifest page count does not shrink to `limit`.

## Constraints & done-when
- Follow this repo's CLAUDE.md and my account-level working agreement; commit as
  one logical, conventional, attributed commit.
- `ruff format . && ruff check .` clean; `pytest` green.
- Optional live check: with a complete manifest present, `PYTHONPATH=src python
  -m aip_downloader --limit 1` leaves the other pages' records intact and a
  subsequent full run reports `304`/skips for unchanged pages instead of
  re-downloading.
