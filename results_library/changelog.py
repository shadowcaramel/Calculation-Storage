"""
Hand-written history of what was added to the calculation library.

``changelog.json`` lives at the library root and is never written by a build.
Each entry is a sentence, not a diff of bundle ids: a rebuild has no memory of
the previous catalog. A missing or unreadable file yields no Changes button.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping

logger = logging.getLogger(__name__)

CHANGELOG_FILENAME = "changelog.json"


@dataclass(frozen=True)
class ChangeEntry:
    """One sentence in the Changes panel."""

    id: str
    date: str
    message: str
    nucleus: str = ""
    lineage: str = ""
    paper: str = ""
    results: List[str] = field(default_factory=list)


def changelog_path(library_root: Path) -> Path:
    return Path(library_root) / CHANGELOG_FILENAME


def load_changelog(library_root: Path) -> List[ChangeEntry]:
    """Read change entries, newest last in the file; callers sort for display.

    A missing file is normal. A malformed file is logged and treated as empty
    so one bad edit cannot stop the calculation site.
    """
    path = changelog_path(library_root)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return []

    raw_entries = data.get("changes") if isinstance(data, Mapping) else None
    if not isinstance(raw_entries, list):
        logger.warning("%s has no 'changes' list", path)
        return []

    entries: List[ChangeEntry] = []
    for item in raw_entries:
        if not isinstance(item, Mapping):
            continue
        entry_id = str(item.get("id") or "").strip()
        message = str(item.get("message") or "").strip()
        if not entry_id or not message:
            logger.warning("Skipping a changelog entry with no id or message")
            continue
        results_raw = item.get("results") or []
        if isinstance(results_raw, str):
            results = [results_raw.strip()] if results_raw.strip() else []
        else:
            results = [str(part).strip() for part in results_raw if str(part).strip()]
        entries.append(
            ChangeEntry(
                id=entry_id,
                date=str(item.get("date") or "").strip(),
                message=message,
                nucleus=str(item.get("nucleus") or "").strip(),
                lineage=str(item.get("lineage") or "").strip().lower(),
                paper=str(item.get("paper") or "").strip(),
                results=results,
            )
        )
    return entries


def newest_first(entries: List[ChangeEntry]) -> List[ChangeEntry]:
    """Date descending, then id, so the unread dot has a stable newest entry."""

    def key(entry: ChangeEntry) -> tuple:
        # Empty dates sort last when reversed (they are not "newer").
        return (entry.date or "", entry.id)

    return sorted(entries, key=key, reverse=True)
