"""
The human layer: notes, curation status, and tags.

``annotations.toml`` lives at the library root, is hand-edited, and is **never**
written by any tool here. The build only reads it and merges it in by result id.
That separation is what makes the machine layer safely disposable: the catalog,
the site, and the Excel view can all be deleted and rebuilt without touching a
single word of what a human wrote.

Anything set in annotations wins over the value stored in ``result.json``, since
the record only ever carries the default ``status = "probing"``.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Mapping

logger = logging.getLogger(__name__)

ANNOTATIONS_FILENAME = "annotations.toml"

#: Keys a human may set. Anything else is reported by the lint pass, because a
#: typo in a key would otherwise silently do nothing.
ANNOTATION_KEYS = ("status", "title", "tags", "note", "outcome")

#: Curation states, from exploratory to published.
STATUSES = ("probing", "working", "published", "superseded")


def annotations_path(library_root: Path) -> Path:
    return Path(library_root) / ANNOTATIONS_FILENAME


def load_annotations(library_root: Path) -> Dict[str, Dict[str, Any]]:
    """Read the annotations overlay, keyed by result id.

    A missing file is normal (nothing has been curated yet) and yields an empty
    overlay. A malformed file is reported and also yields an empty overlay rather
    than aborting the build, so one bad edit cannot make the whole library
    unreadable.
    """
    path = annotations_path(library_root)
    if not path.exists():
        return {}

    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return {}

    overlay: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(value, Mapping):
            overlay[key] = dict(value)
        else:
            logger.warning(
                "Ignoring top-level key %r in %s: expected a table keyed by "
                "result id.",
                key,
                path,
            )
    return overlay


def merge_annotation(record: Dict[str, Any], annotation: Mapping[str, Any]) -> Dict[str, Any]:
    """Overlay one annotation onto a record, returning the display fields."""
    merged = {
        "status": record.get("status", "probing"),
        "title": None,
        "tags": [],
        "note": None,
        "outcome": None,
    }
    if not annotation:
        return merged

    if annotation.get("status"):
        merged["status"] = str(annotation["status"])
    if annotation.get("title"):
        merged["title"] = str(annotation["title"])
    tags = annotation.get("tags")
    if tags:
        merged["tags"] = [str(t) for t in (tags if isinstance(tags, list) else [tags])]
    if annotation.get("note"):
        merged["note"] = str(annotation["note"])
    if annotation.get("outcome"):
        merged["outcome"] = str(annotation["outcome"])
    return merged


def lint_annotations(
    overlay: Mapping[str, Mapping[str, Any]],
    known_ids: set[str],
) -> List[str]:
    """Report unusable annotations: unknown keys, bad status, orphaned ids."""
    problems: List[str] = []

    for result_id, annotation in overlay.items():
        unknown = sorted(set(annotation) - set(ANNOTATION_KEYS))
        if unknown:
            problems.append(
                f"{result_id}: unknown annotation key(s) {unknown}; expected any "
                f"of {list(ANNOTATION_KEYS)}"
            )

        status = annotation.get("status")
        if status is not None and str(status) not in STATUSES:
            problems.append(
                f"{result_id}: status {status!r} is not one of {list(STATUSES)}"
            )

        if result_id not in known_ids:
            # Usually a pruned bundle or a typo in the id. Worth saying, because
            # the note is invisible until the id matches.
            problems.append(
                f"{result_id}: annotation does not match any stored result, so it "
                f"has no effect"
            )

    return problems
