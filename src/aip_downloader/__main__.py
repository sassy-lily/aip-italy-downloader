"""Command-line entry point: ``python -m aip_downloader``."""

from __future__ import annotations

import argparse
import asyncio
import sys

from .auth import EnavAuth
from .config import Settings
from .discover import EnavDiscoverer
from .logging_setup import configure_logging, get_logger
from .pipeline import run
from .version import EnavVersionProvider

logger = get_logger("aip_downloader")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aip_downloader",
        description="Download the current active Italian AIP as per-version PDFs.",
    )
    parser.add_argument("--output-dir", help="Override AIP_OUTPUT_DIR.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and order pages without downloading.",
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Re-download every page even if already present/unchanged.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N pages (for testing).",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Force a fresh login, discarding any saved session.",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging(args.log_level)

    settings = Settings.from_env()
    if args.output_dir:
        from pathlib import Path

        settings.output_dir = Path(args.output_dir)

    if args.login and settings.session_path.exists():
        settings.session_path.unlink()
        logger.info("discarded saved session (forcing fresh login)")

    if not args.dry_run:
        try:
            settings.require_credentials()
        except ValueError as exc:
            logger.error("%s", exc)
            return 2

    try:
        asyncio.run(
            run(
                settings,
                auth=EnavAuth(),
                version_provider=EnavVersionProvider(),
                discoverer=EnavDiscoverer(),
                dry_run=args.dry_run,
                force_full=args.force_full,
                limit=args.limit,
            )
        )
    except NotImplementedError as exc:
        logger.error("Not yet implemented (awaiting recon): %s", exc)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
