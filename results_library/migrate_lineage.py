"""One-shot move of unprefixed bundles under ``bundles/{lineage}/``.

Catalog builds never move files. This command is the exception: it relocates
bundles that still sit directly under ``bundles/`` into ``modern/`` or
``legacy/``, and writes the ``lineage`` field into ``result.json``.

Classification is by annotation tag, not by date:

* ``legacy`` if ``annotations.toml`` has tag ``legacy-code``
* ``modern`` otherwise

Result ids do not change, so annotation and comparison keys stay valid.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from results_library.annotations import load_annotations
from results_library.catalog import BUNDLES_DIRNAME, scan_bundles
from results_library.migrate_paths import _prune_empty_parents
from results_schema.slugs import (
    DEFAULT_LINEAGE,
    LINEAGES,
    bundle_dir_segments,
    lineage_prefix,
)

logger = logging.getLogger(__name__)

LEGACY_CODE_TAG = "legacy-code"


@dataclass
class PlannedMove:
    result_id: str
    lineage: str
    old_dir: Path
    new_dir: Path
    record: Dict


@dataclass
class MigrationReport:
    moved: List[PlannedMove] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _tags_of(annotation: Dict) -> List[str]:
    tags = annotation.get("tags") or []
    if isinstance(tags, str):
        return [tags]
    return [str(item) for item in tags]


def _lineage_for(result_id: str, annotations: Dict[str, Dict]) -> str:
    tags = _tags_of(annotations.get(result_id) or {})
    if LEGACY_CODE_TAG in tags:
        return "legacy"
    return DEFAULT_LINEAGE


def plan_lineage_folder_moves(library_root: Path) -> Tuple[List[PlannedMove], List[str]]:
    """Inspect on-disk bundles and return the moves a rewrite would perform."""
    library_root = Path(library_root)
    scan = scan_bundles(library_root)
    annotations = load_annotations(library_root)
    bundles_root = library_root / BUNDLES_DIRNAME
    planned: List[PlannedMove] = []
    skipped: List[str] = []

    for scanned in scan.records:
        result_id = scanned.result_id or str(scanned.path)
        try:
            relative = scanned.bundle_dir.relative_to(bundles_root).as_posix()
        except ValueError:
            skipped.append(f"{result_id}: not under {bundles_root}")
            continue
        prefix = lineage_prefix(relative)
        if prefix in LINEAGES:
            skipped.append(f"{result_id}: already under {prefix}/")
            continue

        try:
            raw = json.loads(scanned.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            skipped.append(f"{scanned.path}: {exc}")
            continue
        if not isinstance(raw, dict):
            skipped.append(f"{scanned.path}: expected a JSON object")
            continue

        lineage = _lineage_for(result_id, annotations)
        rewritten = dict(raw)
        rewritten["lineage"] = lineage
        new_dir = bundles_root.joinpath(*bundle_dir_segments(lineage, result_id))
        planned.append(
            PlannedMove(
                result_id=result_id,
                lineage=lineage,
                old_dir=scanned.bundle_dir,
                new_dir=new_dir,
                record=rewritten,
            )
        )
    return planned, skipped


def migrate_lineage_folders(
    library_root: Path, *, dry_run: bool = False
) -> MigrationReport:
    """Move unprefixed bundles under ``modern/`` or ``legacy/``."""
    library_root = Path(library_root)
    report = MigrationReport()
    planned, skipped = plan_lineage_folder_moves(library_root)
    report.skipped.extend(skipped)
    bundles_root = library_root / BUNDLES_DIRNAME

    for item in planned:
        if item.new_dir.exists() and item.new_dir.resolve() != item.old_dir.resolve():
            report.errors.append(
                f"cannot move {item.result_id}: destination already exists "
                f"({item.new_dir})"
            )
            continue
        if dry_run:
            report.moved.append(item)
            continue
        try:
            item.new_dir.parent.mkdir(parents=True, exist_ok=True)
            if item.new_dir.resolve() != item.old_dir.resolve():
                shutil.move(str(item.old_dir), str(item.new_dir))
            (item.new_dir / "result.json").write_text(
                json.dumps(item.record, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            _prune_empty_parents(item.old_dir.parent, bundles_root)
            report.moved.append(item)
        except OSError as exc:
            report.errors.append(f"{item.result_id}: {exc}")

    return report
