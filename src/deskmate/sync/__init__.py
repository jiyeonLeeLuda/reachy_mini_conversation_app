"""Track A: Chrome bookmarks → ``bookmarks/<profile>/YYYY/*.md`` mirror (§2.4).

Public entry point (contract for tools and the CLI):

    sync_profiles(settings, *, profiles=None, now=None) -> SyncReport

``chrome`` reads Chrome's files, ``naming`` owns the filename rule and URL
key, ``mirror`` applies the §2.4 update/archive policy through ``store``.
``python -m deskmate.sync`` runs one sync by hand.
"""

from deskmate.sync.mirror import sync_profiles
from deskmate.sync.naming import normalize_url, build_filename, build_bookmark_path
from deskmate.sync.report import SyncReport


__all__ = ["SyncReport", "build_bookmark_path", "build_filename", "normalize_url", "sync_profiles"]
