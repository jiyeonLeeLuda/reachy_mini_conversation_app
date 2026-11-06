"""Create a DeskMate demo bookmark repository from the test fixtures.

Usage (from the project root, venv active)::

    python scripts/deskmate_demo_setup.py ~/deskmate-demo

It copies ``tests/deskmate/fixtures/repo_sample`` (3 summarized bookmarks +
one ready insight note for 2026-10-31..2026-11-06) and the fake Chrome
``User Data`` directory, then prints the ``.env`` lines to paste. With these,
``get_insight(since="2026-10-31", until="2026-11-06")`` answers ``ready`` in the
emulator without any network or LLM key (M1 대화 품질 선검증).
"""

from __future__ import annotations
import sys
import shutil
import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "deskmate" / "fixtures"


def main(argv: list[str] | None = None) -> int:
    """Copy the fixtures and print the environment lines."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="directory to create (must not exist)")
    args = parser.parse_args(argv)
    target: Path = args.target.expanduser().resolve()
    if target.exists():
        print(f"refusing to overwrite existing directory: {target}", file=sys.stderr)
        return 2

    shutil.copytree(FIXTURES / "repo_sample", target / "repo")
    shutil.copytree(FIXTURES / "chrome_user_data", target / "User Data")

    print("Demo repository created. Add these lines to your .env:\n")
    print(f"DESKMATE_BOOKMARK_REPO={target / 'repo'}")
    print(f"DESKMATE_CHROME_USER_DATA_DIR={target / 'User Data'}")
    print("DESKMATE_CHROME_PROFILES=Default")
    print("REACHY_MINI_CUSTOM_PROFILE=deskmate_ko")
    print("\nThen say: '10월 31일부터 11월 6일까지 북마크 얘기하자' (ready note) or")
    print("'이번 주 북마크 얘기하자' (generating → build_insight with FakeLLM unless GEMINI_API_KEY is set).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
