"""Manual sync run: ``python -m deskmate.sync [--profile NAME ...] [--repo PATH] [--chrome-dir PATH] [-v]``."""

import sys
import logging
import argparse
from pathlib import Path
from dataclasses import replace

from dotenv import find_dotenv, load_dotenv

from deskmate.settings import load_settings
from deskmate.sync.mirror import sync_profiles


def main(argv: list[str] | None = None) -> int:
    """Run one sync with settings from ``.env``/environment and print a per-profile summary."""
    parser = argparse.ArgumentParser(
        prog="python -m deskmate.sync", description="Mirror Chrome bookmarks to markdown."
    )
    parser.add_argument(
        "--profile", action="append", help="Chrome profile folder to sync (repeatable; overrides the allow list)"
    )
    parser.add_argument("--repo", type=Path, help="bookmark repository (overrides DESKMATE_BOOKMARK_REPO)")
    parser.add_argument(
        "--chrome-dir", type=Path, help="Chrome User Data directory (overrides DESKMATE_CHROME_USER_DATA_DIR)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)
    settings = load_settings()
    if args.repo is not None:
        settings = replace(settings, bookmark_repo=args.repo)
    if args.chrome_dir is not None:
        settings = replace(settings, chrome_user_data_dir=args.chrome_dir)
    if not settings.configured:
        print("DESKMATE_BOOKMARK_REPO is not set (or pass --repo)", file=sys.stderr)
        return 2

    report = sync_profiles(settings, profiles=args.profile)
    for profile in report.profiles:
        print(
            f"{profile}: created={report.created[profile]} updated={report.updated[profile]} "
            f"archived={report.archived[profile]} excluded={report.excluded[profile]}"
        )
    for profile in report.skipped_profiles:
        print(f"{profile}: skipped (not in allow list)")
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0 if report.profiles else 1


if __name__ == "__main__":
    raise SystemExit(main())
