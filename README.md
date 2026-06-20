# aip-downloader

Downloads the PDF pages of the **current active** Italian AIP (Aeronautical
Information Publication) from ENAV's portal, saving each page individually,
named by section and page, in true publication order, as a per-version snapshot.

> Status: in development. The site-specific login/navigation internals are filled
> in after a recon phase (see `docs/BUILD_PROMPT.md` and `docs/RECON.md`).

## Requirements

- Python 3.14
- A free ENAV account (the AIP is free but requires registration)

## Setup

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt   # use requirements.txt for runtime only
cp .env.example .env                   # then fill in AIP_USER / AIP_PASS
```

## Usage

The package lives under `src/` and is run without installation, so put `src`
on `PYTHONPATH`:

```bash
PYTHONPATH=src python -m aip_downloader            # download the current active AIP
PYTHONPATH=src python -m aip_downloader --dry-run  # discover + plan without downloading
```

Useful flags: `--output-dir`, `--force-full`, `--log-level`.

Output is written to `AIP_OUTPUT_DIR/<version>/`, with a `manifest.json` per
version recording each page and its download state.

## Development

```bash
ruff format . && ruff check .
pytest
```

Tests never touch the live site — HTTP is mocked with `respx`.
