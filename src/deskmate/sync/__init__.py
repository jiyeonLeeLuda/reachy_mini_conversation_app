"""Track A: Chrome bookmarks → ``bookmarks/<profile>/YYYY/*.md`` mirror (§2.4).

Public entry point (contract for tools and the CLI):

    sync_profiles(settings, *, profiles=None, now=None) -> SyncReport

Implementation lives in submodules written by track A; this file only pins
the signature so other tracks can import it before the implementation lands.
"""

from __future__ import annotations
from datetime import datetime
from dataclasses import field, dataclass

from deskmate.settings import DeskmateSettings


@dataclass
class SyncReport:
    """What one sync run did, per profile folder name."""

    profiles: list[str] = field(default_factory=list)
    skipped_profiles: list[str] = field(default_factory=list)  # present on disk but not allowed
    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    archived: dict[str, int] = field(default_factory=dict)
    excluded: dict[str, int] = field(default_factory=dict)  # private folders etc. (never exposed to the model)
    warnings: list[str] = field(default_factory=list)


def sync_profiles(
    settings: DeskmateSettings,
    *,
    profiles: list[str] | None = None,
    now: datetime | None = None,
) -> SyncReport:
    """Mirror the allowed Chrome profiles into the bookmark repository.

    ``profiles`` overrides the allow list (tests); ``now`` fixes the sync
    timestamp. Implemented in track A (``deskmate.sync.chrome`` / ``mirror``).
    """
    raise NotImplementedError("track A: deskmate.sync is not implemented yet")
