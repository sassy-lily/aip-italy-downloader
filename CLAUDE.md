# aip-downloader

A Python 3.14 tool that authenticates to an AIP (Aeronautical Information
Publication) portal, discovers published PDF documents, and downloads them
locally. **Status: greenfield** — the structure below is the intended target,
not yet built. Update sections as reality lands.

## Open questions (resolve before/while implementing)
- **Auth is Oracle IDCS via SAML SSO** (known). Unverified: how to complete the
  login programmatically, and whether MFA / email verification rules out
  unattended automation. Expect to need a real browser (Playwright); if login
  can't be fully scripted, persist a manual-login session (`storage_state`) and
  reuse it. Record the verified mechanism here once known.
- **Rendering is unverified.** Assume PDF links live in server-rendered HTML and
  build on an HTTP client first. If pages turn out to be JS-rendered (or login
  needs JS), fall back to Playwright — keep browser logic behind the same
  auth/discovery interface so the rest of the code is unaffected.
- **Active-version identification is unverified.** The service landing page lists
  the current active version plus upcoming not-yet-active ones (AIRAC cycle,
  28-day cadence). Discover how to read the active version's id/effective date
  from that page. Record it here.
- **Change-distinction is unverified.** It is not yet known whether the site
  exposes which pages changed between versions (e.g. a GEN 0.4 checklist of
  effective pages, an AIRAC AMDT list, NEW/CHG markers, or honored HTTP
  `ETag`/`Last-Modified`). Recon must find out; the delta optimization depends
  on it (see Versioning).

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
