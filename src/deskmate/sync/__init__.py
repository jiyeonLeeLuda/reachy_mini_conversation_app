"""Track A: Chrome bookmarks → ``bookmarks/<profile>/YYYY/*.md`` mirror (§2.4).

Public entry point (contract for tools and the CLI):

    sync_profiles(settings, *, profiles=None, now=None) -> SyncReport

``chrome`` reads Chrome's files, ``naming`` owns the filename rule and URL
key, ``mirror`` applies the §2.4 update/archive policy through ``store``,
``git_mirror`` (M9, optional) turns the files into back-dated git commits.
``python -m deskmate.sync`` runs one sync by hand (``--git-rebuild`` rebuilds
the git history).
"""

from deskmate.sync.mirror import sync_profiles
from deskmate.sync.naming import normalize_url, build_filename, build_bookmark_path
from deskmate.sync.report import SyncReport
from deskmate.sync.git_mirror import MirrorReport, GitMirrorError, rebuild_history


__all__ = [
    "GitMirrorError",
    "MirrorReport",
    "SyncReport",
    "build_bookmark_path",
    "build_filename",
    "normalize_url",
    "rebuild_history",
    "sync_profiles",
]
