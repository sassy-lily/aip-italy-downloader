# Task: build the Italian AIP PDF downloader

Build the application described in this repo's CLAUDE.md: a Python 3.14 tool that
logs into ENAV's portal and downloads the PDF pages of the **current active
version** of the Italian AIP (Aeronautical Information Publication), saving each
page as an individual, correctly-named, correctly-ordered file.

Follow this repo's CLAUDE.md and my account-level working agreement at all times.
In particular: resolve ambiguity by asking me before guessing; verify anything
version- or API-specific against current sources rather than memory; and commit
in small, conventional, attributed increments as you go — do not batch.

## What is known

The AIP is free but requires a free account. Auth is **Oracle Identity Cloud
Service via SAML SSO** — expect a multi-redirect, JS-driven login, so plan on
driving a real browser (Playwright) to establish the session. The observed
access flow is:

1. https://www.enav.it/
2. https://www.enav.it/login-required
3. https://www.enav.it/samllogin
4. https://www.enav.it/services/list
5. https://www.enav.it/services/list/aip
6. https://onlineservices.enav.it/enavWebPortalStatic/AIP/AIP/defaultInt.html  ← the AIP service landing page

The site does **not** follow web best practices. Treat navigation and feature
discovery as a research problem — do not assume conventional markup, routes, or
APIs. Verify everything against the live site.

The active version changes over time on the **AIRAC cycle** (~28 days): the
landing page lists the current active version **plus upcoming, not-yet-active
versions**. Act on the active version only. When the active version changes, its
pages must be (re-)downloaded so local files reflect the new version.

Credentials: I will place a real ENAV account in a gitignored `.env`
(`AIP_USER`, `AIP_PASS`). You are authorized to drive a browser against the live
site to investigate and to download. This is a free account downloading freely-
published documents I'm entitled to — but stay polite (see constraints).

## Unknowns you must discover (Phase 1)

These are the core research targets. Do not assume — find out by inspecting the
live site:

- How to complete the SAML/IDCS login programmatically, and whether MFA/email
  verification makes full automation impractical (if so, propose manual-login-
  once + persisted session reuse).
- How to identify, **from the AIP service landing page**, the link to the
  **current active version** (AIRAC cycle / effective date).
- How to enumerate the links to **all pages** of that active version, across all
  sections (GEN / ENR / AD, etc.).
- How to obtain the **PDF** for each individual page.
- The real ordering of pages within and across sections, so output order matches
  the official document order.
- **Whether the site reveals which pages changed between versions** — e.g. a
  GEN 0.4 *checklist of effective pages*, an *AIRAC AMDT* change list, NEW/CHG
  markers, or honored HTTP `ETag`/`Last-Modified`. This determines whether
  re-downloads can be a precise delta or must be a full fetch.

## Workflow (three phases — stop at the gate)

**Phase 1 — Recon.** Drive the live site and figure out the unknowns above.
Write your findings to `docs/RECON.md`: the actual login mechanism, the exact
requests/elements used to find the active version, page enumeration, and per-page
PDF retrieval — with concrete URLs, selectors, and any quirks. Update the "Open
questions" section of CLAUDE.md to reflect what's now known.

**Phase 2 — Plan.** Propose an implementation plan grounded in the recon:
module breakdown, login strategy (your recommendation), the file naming +
ordering scheme, dependency list, and the polite-scraping parameters. **Then stop
and wait for my approval before writing application code.**

**Phase 3 — Implement.** Build it per the approved plan and CLAUDE.md
conventions, committing in logical increments.

## Functional requirements

- Save each AIP page as its **own PDF** file under the active version's directory
  (`AIP_OUTPUT_DIR/<version>/...`).
- Each filename must reflect the **section and page** it represents.
- Files must sort in the **true page order** of the publication. A monotonic
  numeric prefix is acceptable (e.g. `0137_ENR-1.1.pdf`); if you find a cleaner
  scheme that preserves order and stays human-readable, propose it in Phase 2.
- **Versioned snapshots, history kept.** Each active version downloads into its
  own `<version>` namespace; never overwrite a previous version's files.
- **Act on the active version only**; ignore upcoming not-yet-active versions.
- **Re-download on version change.** When the active version changes, fetch the
  new version. Re-fetch only changed pages **if** a reliable delta signal exists
  (per the recon finding above); otherwise full-download. Correctness must never
  depend on the delta signal.
- Maintain a **per-version manifest** (`<version>/manifest.json`) recording each
  page's section, page id, source URL, ordering index, filename, content hash,
  and HTTP validators — used for change-detection, idempotent resume, and order.
- **Optional / not required:** merging all pages into one ordered combined PDF.
  Only attempt after the core feature works.

## Constraints

- Login session and credentials: via `.env` only; never hardcode or log secrets.
- Be polite to the live server: cap concurrency, delay between requests, set a
  descriptive User-Agent, and back off on errors. Never parallelize aggressively
  against the auth or download endpoints.
- Idempotent: skip pages already downloaded and support resuming an interrupted
  run.
- Respect robots.txt / Terms of Service; only download what the account may access.

## Done when

- `docs/RECON.md` documents how the site actually works.
- Running the tool against the live site downloads the full current active AIP as
  individually-named, correctly-ordered PDFs under `AIP_OUTPUT_DIR/<version>/`.
- A second run on the same active version re-downloads nothing (idempotent) and a
  killed run resumes cleanly.
- When the active version changes, the new version is fetched into its own
  snapshot without disturbing prior versions, re-fetching only changed pages
  where a reliable delta signal was found.
