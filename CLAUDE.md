# aip-downloader

A Python 3.14 tool that authenticates to an AIP (Aeronautical Information
Publication) portal, discovers published PDF documents, and downloads them
locally. **Status: functional** — the full pipeline (login → active version →
discover → download → manifest) is implemented and verified end-to-end against
the live ENAV site for the main eAIP (GEN/ENR/AD, 907 pages). See the verified
mechanics below and docs/RECON.md.

## Site mechanics (verified in Phase 1 — full detail in docs/RECON.md)
- **Auth:** Oracle IDCS → OAM/SAML, password-only (no MFA). Headless Playwright
  login works; persist `storage_state.json` and reuse the cookies in httpx for
  the whole crawl/download (no browser after login).
- **Active version:** the `<a>` under the `Uscita Corrente` heading on
  `…/AIP/AIP/defaultInt.html`. Edition folder e.g. `(A06-26)_2026_06_11`.
- **Enumeration:** parse `<edition>/eAIP/menu.html` for `LI-<id>-it-IT.html`
  links (907 pages for A06-26: GEN 28, ENR 408, AD 471).
- **Per-page PDF:** strip the language suffix, map `/eAIP`→`/documents/PDF`,
  `.html`→`.pdf` — i.e. `documents/PDF/LI-<id>.pdf` (one bilingual PDF per page).
- **Ordering:** use `menu.html` document order (numeric sort is wrong for AD).
- **Delta:** PDFs expose `ETag` + `Last-Modified` → `HTTP_VALIDATORS`.

## Open questions
- Whether to also fetch `eSUP` (supplements) / `eAIC` (circulars) — same PDF
  mechanism, currently treated as optional follow-on to the main eAIP.
- Whether any page needs the `Merged_…` PDF variant (`commands.js` MergeFileCheck)
  rather than the plain per-page PDF.

## Environment & setup
- Python **3.14**, plain `venv` + `pip` (no uv/poetry).
- Bootstrap:
  ```
  python3.14 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt          # runtime
  pip install -r requirements-dev.txt       # lint/test (ruff, pytest, respx)
  cp .env.example .env                      # then fill in secrets
  ```

## Common commands
- Run: `python -m aip_downloader`
- Format / lint: `ruff format . && ruff check .`
- Tests: `pytest`

## Configuration & secrets
- All secrets come from environment variables, loaded in dev from a **gitignored
  `.env`** via `python-dotenv`. Keep a committed `.env.example` with empty keys.
- Required: `AIP_USER`, `AIP_PASS`. Also env-driven: `AIP_BASE_URL`,
  `AIP_OUTPUT_DIR`.
- Never hardcode credentials, cookies, or tokens; never log them. `.env` must
  stay in `.gitignore`.

## Architecture (intended)
- `src/` layout, package `src/aip_downloader/`, split by concern so each piece is
  testable in isolation:
  - `auth.py` — log in, hold/refresh the session.
  - `version.py` — read the active version id/effective date from the landing
    page; detect changes against stored state.
  - `discover.py` — crawl/parse pages, yield PDF URLs (+ pagination, ordering).
  - `download.py` — fetch PDFs, write to the active version's dir, skip/resume.
  - `manifest.py` — read/write the per-version manifest (see Versioning).
  - `__main__.py` — CLI entry point and wiring.
- HTTP via **httpx** (async client); parse HTML with **BeautifulSoup**.
- Inject clients and paths (don't construct them deep in the call tree) so tests
  can pass fakes.

## Versioning & state
- The active AIP version changes on the AIRAC cycle (~28 days). On every run,
  read the active version id from the landing page and act on **that version
  only** — ignore upcoming not-yet-active versions.
- **Versioned snapshots, history kept.** Each version downloads into its own
  namespace: `AIP_OUTPUT_DIR/<version>/...` (e.g. effective date or AIRAC id).
  Never overwrite a prior version's tree.
- **Per-version manifest** (`AIP_OUTPUT_DIR/<version>/manifest.json`) is the
  source of truth: for each page records section, page id, source URL, ordering
  index, output filename, content hash, and HTTP validators (`ETag` /
  `Last-Modified`). It drives change-detection, idempotent resume, and ordering.
- **On version change**, fetch the new version. Re-fetch only changed pages when
  a reliable delta signal exists (site change metadata, or hash / HTTP
  validators vs. the previous manifest); otherwise fall back to a full download.
  Correctness never depends on the delta signal — full re-download is always the
  safe baseline.
- Idempotency is scoped **per version**: within a version, skip pages already
  present (by manifest identity/hash) and resume cleanly after interruption.

## Scraping conduct (non-negotiable)
- Only fetch content the authenticated account is entitled to. Check
  `robots.txt` and the site's Terms of Service before crawling.
- Be polite: cap concurrency, add a delay between requests, set a descriptive
  `User-Agent`, and retry transient failures with exponential backoff.
- Idempotent runs: skip files already downloaded (compare size/hash) and support
  resuming an interrupted run. Never hammer the auth server with parallelism.

## Conventions
- Type hints on all public functions; `pathlib` over `os.path`; the stdlib
  `logging` module over `print` for diagnostics.
- Keep network, parsing, and storage concerns separate.
- Tests use `pytest` and mock HTTP (`respx` or `httpx.MockTransport`) — never
  hit the live AIP site from tests.
