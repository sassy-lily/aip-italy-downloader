# aip-downloader

A Python 3.14 tool that authenticates to an AIP (Aeronautical Information
Publication) portal, discovers published PDF documents, and downloads them
locally. **Status: greenfield** — the structure below is the intended target,
not yet built. Update sections as reality lands.

## Open questions (resolve before/while implementing)
- **Auth flow is unverified.** Inspect the real login before committing to an
  approach: is it a form POST + session cookie, HTTP Basic/token, or a
  JS/SSO/MFA flow? Record the answer here once known.
- **Rendering is unverified.** Assume PDF links live in server-rendered HTML and
  build on an HTTP client first. If pages turn out to be JS-rendered (or login
  needs JS), fall back to Playwright — keep browser logic behind the same
  auth/discovery interface so the rest of the code is unaffected.

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
  - `discover.py` — crawl/parse pages, yield PDF URLs (+ pagination).
  - `download.py` — fetch PDFs, write to `AIP_OUTPUT_DIR`, skip/resume.
  - `__main__.py` — CLI entry point and wiring.
- HTTP via **httpx** (async client); parse HTML with **BeautifulSoup**.
- Inject clients and paths (don't construct them deep in the call tree) so tests
  can pass fakes.

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
