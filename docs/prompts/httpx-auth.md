# Task: replace Playwright login with an httpx-only auth flow (remove Playwright)

## Context
Auth currently uses Playwright (headless Chromium, ~150 MB) only to obtain the
SAML session cookies; the entire crawl/download already runs over httpx. A spike
proved the Oracle IDCS → OAM/SAML login is fully replayable with httpx alone
(every step's tokens come from the prior response; **no X-CSRF-TOKEN needed**, a
minimal `device` object is accepted). Removing Playwright collapses the app to
pure Python (httpx + beautifulsoup4 + lxml + python-dotenv), which makes it
small and trivial to package for end users.

Keep the `AuthProvider` Protocol (`interfaces.py`) unchanged so `pipeline`,
`discover`, `download`, `version`, and `manifest` are untouched. Only `auth.py`
(and dependency/doc cleanup) changes.

## Verified login chain (reproduce exactly; do NOT re-spike)
Use one `httpx.AsyncClient(follow_redirects=True)` with a **browser-like
User-Agent** (IDCS is picky); its cookie jar accumulates the session.

1. `GET` `version.LANDING_URL` → redirects land on `/sso/v1/user/login`, whose
   body is an **auto-submit HTML form**: `action` = the IDCS `/ui/v1/signin` URL,
   hidden inputs `signature`, `state`, `loginCtx`. Parse with BeautifulSoup
   (first `<form>`, all `<input name=…>`). Derive the IDCS base from the action
   host.
2. `POST` that action with those fields (form-encoded).
3. `POST` `{idcs_base}/ui/v1/api/user/secure/login` with JSON, header
   `content-type: application/json` (no CSRF header):
   ```json
   {"op":"cred_submit","credentials":{"username":"…","password":"…",
     "device":"{\"screenWidth\":1280,\"screenHeight\":720}"}}
   ```
   Response JSON: `{"success":true,"nextOp":"postRedirect",
   "redirectUrl":".../fed/v1/user/response/login","postParams":{"OCIS_REQ":"…"}}`.
4. `POST` `redirectUrl` with `postParams` (form-encoded) → body is another
   auto-submit form: `action` = `https://auth.enav.it/oam/server/fed/sp/sso`,
   fields `RelayState`, `SAMLResponse`.
5. `POST` that form → redirects back to the authenticated portal (200).

After step 5 the client's cookie jar holds the session (onlineservices.enav.it
OAM cookies etc.).

## Implementation
**`src/aip_downloader/auth.py`** — rewrite `EnavAuth.get_session(settings)`:
- Keep the existing **session-reuse** behaviour: if `settings.session_path`
  exists, return `SessionContext(storage_state_path=str(path))` without logging
  in. Otherwise `settings.require_credentials()` then run the chain above.
- Persist the resulting cookies to `settings.session_path` in the **same JSON
  shape** the codebase already reads (`{"cookies":[{"name","value","domain",
  "path"},…]}`), by serialising the httpx cookie jar
  (`client.cookies.jar` → `http.cookiejar.Cookie` has `.name/.value/.domain/
  .path`). This keeps `http_client.cookies_from_storage_state` and the pipeline
  unchanged.
- Return `SessionContext(storage_state_path=str(settings.session_path))`.
- Remove all Playwright imports/usage and the `USERNAME_SEL`/`PASSWORD_SEL`/
  `PORTAL_GLOB` browser bits.
- **Error handling:** if step 3 returns `success` false or `nextOp != "postRedirect"`
  (e.g. an MFA/adaptive challenge), raise a clear error explaining the account
  may require interactive auth. **Never log credentials** (no full request bodies).

**Dependency & doc cleanup:**
- `requirements.txt`: remove the `playwright` pin.
- `README.md`: remove the `playwright install chromium` step and any Playwright
  mention.
- `CLAUDE.md`: update the stack line (drop "Playwright for login") and the
  "Auth" verified-mechanics bullet to say login is an httpx SAML replay.
- `docs/RECON.md` section 1: add a one-line note that auth is now httpx-only
  (Playwright no longer required).
- Optional: rename `cookies_from_storage_state` → `cookies_from_session_file`
  (it's no longer Playwright-specific); update call sites if you do.

## Tests
**`tests/test_auth.py`** (new) — now unit-testable since there's no browser. With
`respx`, mock the chain: `/sso/v1/user/login` (auto-submit form HTML),
`/ui/v1/signin`, `secure/login` (JSON success), `fed/v1/user/response/login`
(SAML auto-submit form HTML), and the OAM `fed/sp/sso` POST. Assert:
- `get_session` returns a `SessionContext` whose `storage_state_path` file exists
  and contains the expected session cookies.
- the JSON posted to `secure/login` has `op == "cred_submit"` and carries the
  username (use a fake credential).
- session reuse: when `session_path` already exists, no HTTP calls are made.
- a `success:false` secure/login response raises a clear, credential-free error.

Existing `FakeAuth` in `test_pipeline.py` is unaffected.

## Constraints & done-when
- Follow CLAUDE.md and my account-level working agreement; commit in logical,
  conventional, attributed increments (e.g. `feat: replace Playwright login with
  httpx SAML replay`, then a `chore:`/`docs:` for dependency/doc cleanup). No push.
- `ruff format . && ruff check .` clean; `pytest` green.
- Live check: delete any saved session, then
  `PYTHONPATH=src python -m aip_downloader --login --limit 3` downloads pages
  successfully with **no Playwright/Chromium involved**.
- After verifying, Playwright is gone from runtime; note that its browser cache
  (`~/.cache/ms-playwright`) and the venv package can be removed separately.

## Caveats to preserve in docs
- The flow hits IDCS internal endpoints tied to a versioned JS bundle, so an IDCS
  upgrade could change it (more brittle than the browser path). And it assumes no
  adaptive MFA — if ENAV enables MFA/device-trust, interactive auth would need to
  be reintroduced. Record both in CLAUDE.md open questions.
