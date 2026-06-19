# Recon findings — ENAV eAIP Italia (Phase 1)

Investigated live on 2026-06-20 against the active edition **A06-26** (effective
11 Jun 2026). All URLs verified with the authenticated session. The portal is an
**IDS AIRNAV eAIP** package (classic frameset + JS), served as static files
behind Oracle SSO.

## 1. Authentication — solved, headless, no MFA

Login is **Oracle IDCS** federated to the portal via **OAM/SAML**. Driving it
headless with Playwright works end to end (password-only account, no MFA/OTP).

Redirect chain on submit:
`defaultInt.html` → `auth.enav.it/oam/server/obrareq.cgi` → IDCS
`/fed/v1/idp/sso` → (POST creds) → IDCS `/fed/v1/user/response` →
`auth.enav.it/oam/server/fed/sp/sso` → `onlineservices.enav.it/obrar.cgi` →
authenticated `defaultInt.html` (title "eAIP ITALY").

IDCS sign-in form (at `…/ui/v1/signin`):
- username: `#idcs-signin-basic-signin-form-username`
- password: `[id="idcs-signin-basic-signin-form-password|input"]` (literal `|` in
  the id — use an attribute selector)
- submit: button with exact text `Sign In` (ignore the `Accesso Dipendenti`
  employee-SSO buttons)

**Session reuse:** after login, persisting Playwright `storage_state.json` and
seeding a plain `httpx` client with those cookies fetches protected pages (200).
→ **Strategy: Playwright logs in once, then the entire crawl/download runs over
httpx.** No browser needed after auth.

## 2. Active version — solved (label-based, authoritative)

Landing page `…/AIP/AIP/defaultInt.html` lists editions in three labelled
sections, each an `<h2>` + table:
- **`Uscita Corrente`** → the active edition (row highlighted green `#ADFF2F`)
- **`Prossima Uscita`** → upcoming, not yet active (pink `#FF9999`)
- **`Uscite Scadute (Archiviate)`** → expired

Rule: the active edition is the `<a>` in the table under the **`Uscita Corrente`**
heading. Cross-check: its effective date ≤ today and is the latest such.

Edition link (note **backslash** separators in hrefs — normalise to `/`):
`(A06-26)_2026_06_11\index.html`. From it derive:
- `version_id` = `(A06-26)_2026_06_11` (slugify for the output dir → `A06-26_2026_06_11`)
- `effective_date` = `2026-06-11`
- `airac_cycle` = `06/2026` (from the "AIRAC AMENDMENT 06/2026 …" change reason)

## 3. Edition structure

`(<edition>)/index.html` is a frameset → nav `eAIP/menu.html` (the TOC) + content.
Pages live under `<edition>/eAIP/` as **per-language HTML**:
`LI-<PAGE_ID>-it-IT.html` and `LI-<PAGE_ID>-en-GB.html` (e.g. `LI-GEN 0.4-it-IT.html`).
Sibling trees: `eSUP/` (supplements), `eAIC/` (circulars).

## 4. Page enumeration — solved (907 pages)

Parse `<edition>/eAIP/menu.html` (~11.8 MB, single-quoted hrefs) for links
matching `LI-(GEN|ENR|AD) …-it-IT.html`. Enumerate the **it-IT** set to avoid
double-counting (the PDF is language-neutral; see §5).

Counts for A06-26: **907 unique pages** — GEN 28, ENR 408, AD 471.
`page_id` = the token between `LI-` and `-it-IT.html`, e.g. `GEN 0.4`,
`ENR 1.1`, `AD 2  LIAF - FOLIGNO 1` (aerodrome pages embed ICAO + name + index;
note the double space).

## 5. Per-page PDF — solved (one bilingual PDF per page)

The "PDF" command builds the URL via `readFileAsPdf` in `commands.js`, using
constants from `navigationCommand.js`:
`HTML_FOLDER='/eAIP'`, `PDF_FOLDER='/documents/PDF'`, `lang1='it-IT'`,
`lang2='en-GB'`, `coverPagePDFFile='/LI-Cover Page.pdf'`,
`SUP_FOLDER='/eSUP'`, `AIC_FOLDER='/eAIC'`.

Transform: take the HTML href, **strip the `-it-IT`/`-en-GB` language suffix**,
replace the `/eAIP` path segment with `/documents/PDF`, and swap `.html`→`.pdf`:

```
eAIP/LI-GEN 0.4-it-IT.html  ->  documents/PDF/LI-GEN 0.4.pdf
```

So there is **one bilingual PDF per page** (IT+EN in the official layout), not one
per language. Verified: `…/documents/PDF/LI-GEN 0.4.pdf` → `200 application/pdf`,
`%PDF-1.4`, ~200 KB. Sample probes across GEN/ENR/AD all return `200
application/pdf`. The cover page PDF is the special `documents/PDF/LI-Cover Page.pdf`.

URL caveats: edition folder contains parentheses; hrefs use `\` separators; page
ids contain spaces — URL-encode carefully (spaces → `%20`).

Edge case (defer): `commands.js` `MergeFileCheck` looks for a `Merged_…` /
`name.X.pdf` variant for pages split into sub-parts, falling back to the plain
PDF on 404. The plain per-page PDF is the baseline; merged variants can be added
later if any page needs it.

## 6. Ordering — use menu document order (authoritative)

Component-wise numeric sort of `page_id` is correct for GEN/ENR but **wrong for
AD**, where aerodromes are grouped by ICAO (e.g. all `AD 2  LIRF …` pages
together), not by trailing page number. **Use the order pages appear in
`menu.html`** as the canonical `ordering_index`; `naming.renumber` stamps the
prefix without re-sorting.

## 7. Delta signal — `HTTP_VALIDATORS` (primary)

Each PDF response carries `ETag` (e.g. `"30d85-652648ae90c40"`) and
`Last-Modified` (e.g. `Fri, 22 May 2026 09:20:41 GMT`). On a version change,
conditional requests / validator comparison vs the previous manifest give a
reliable per-page delta → `DeltaSignal.HTTP_VALIDATORS`.

Richer semantic options (defer, optional): **GEN 0.4** is the *checklist of
effective pages*; `eAIP/amendments.js` (~12 KB) is the AMDT change list and could
mark NEW/CHG pages. Not needed for correctness.

## 8. Scope note

This covers the main **eAIP** (GEN/ENR/AD). `eSUP` (supplements) and `eAIC`
(circulars) are sibling trees with the same PDF mechanism (`/eSUP` and `/eAIC`
get `/documents/PDF` appended per `readFileAsPdf`). Treat them as an optional
follow-on; the active eAIP is the deliverable.

## 9. Politeness

907 PDFs ≈ ~180 MB per edition. Keep `Semaphore(2)`, ~1 s jittered delay,
conditional requests on re-runs. `robots.txt` does not disallow these paths.
