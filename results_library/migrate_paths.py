"""One-shot rewrite of v1 four-segment bundles into the v2 folder layout.

Catalog builds never move files. This command is the exception: it relocates
bundles so selection sets share a parent folder, rewrites ``result.json`` ids,
and updates annotation / comparison keys that pointed at the old ids.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Tuple

from results_library.catalog import BUNDLES_DIRNAME, scan_bundles
from results_library.comparisons import COMPARISONS_FILENAME
from results_library.migrations.v1_selection_folders import rewrite_v1_record

logger = logging.getLogger(__name__)

ANNOTATIONS_FILENAME = "annotations.toml"


@dataclass
class PlannedMove:
    old_id: str
    new_id: str
    old_dir: Path
    new_dir: Path
    record: Dict


@dataclass
class MigrationReport:
    moved: List[PlannedMove] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    rewritten_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def plan_selection_folder_moves(library_root: Path) -> Tuple[List[PlannedMove], List[str]]:
    """Inspect on-disk bundles and return the moves a rewrite would perform."""
    library_root = Path(library_root)
    scan = scan_bundles(library_root)
    # scan_bundles already applies in-memory migrations, so ids in scan.records
    # are the *new* ids. Use the raw file for the old id.
    planned: List[PlannedMove] = []
    skipped: List[str] = []

    for scanned in scan.records:
        try:
            raw = json.loads(scanned.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            skipped.append(f"{scanned.path}: {exc}")
            continue
        if not isinstance(raw, dict):
            skipped.append(f"{scanned.path}: expected a JSON object")
            continue

        old_id = str(raw.get("id") or "")
        old_parts = old_id.split("/")
        if len(old_parts) >= 5:
            skipped.append(f"{old_id}: already five segments")
            continue
        if len(old_parts) != 4:
            skipped.append(f"{old_id or scanned.path}: not a four-segment v1 id")
            continue

        rewritten = rewrite_v1_record(dict(raw))
        rewritten["schema_version"] = 2
        new_id = str(rewritten.get("id") or "")
        if new_id == old_id:
            skipped.append(f"{old_id}: rewrite left the id unchanged")
            continue

        planned.append(
            PlannedMove(
                old_id=old_id,
                new_id=new_id,
                old_dir=scanned.bundle_dir,
                new_dir=library_root / BUNDLES_DIRNAME / Path(*new_id.split("/")),
                record=rewritten,
            )
        )
    return planned, skipped


def _prune_empty_parents(start: Path, stop: Path) -> None:
    current = start
    try:
        stop_resolved = stop.resolve()
    except OSError:
        stop_resolved = stop
    while current.exists():
        try:
            if current.resolve() == stop_resolved:
                break
        except OSError:
            break
        try:
            next(current.iterdir())
            break
        except StopIteration:
            parent = current.parent
            try:
                current.rmdir()
            except OSError:
                break
            current = parent
        except OSError:
            break


def _replace_ids(text: str, mapping: Mapping[str, str]) -> str:
    """Replace old result ids with new ones, longest first to avoid prefixes."""
    updated = text
    for old_id, new_id in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        updated = updated.replace(old_id, new_id)
    return updated


def _rewrite_sidecar(path: Path, mapping: Mapping[str, str], dry_run: bool) -> bool:
    if not path.exists() or not mapping:
        return False
    original = path.read_text(encoding="utf-8")
    updated = _replace_ids(original, mapping)
    if updated == original:
        return False
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return True


def migrate_selection_folders(
    library_root: Path, *, dry_run: bool = False
) -> MigrationReport:
    """Move v1 bundles into the v2 layout. ``dry_run`` only reports the plan."""
    import shutil

    library_root = Path(library_root)
    report = MigrationReport()
    planned, skipped = plan_selection_folder_moves(library_root)
    report.skipped.extend(skipped)

    mapping = {item.old_id: item.new_id for item in planned}
    bundles_root = library_root / BUNDLES_DIRNAME

    for item in planned:
        if item.new_dir.exists() and item.new_dir.resolve() != item.old_dir.resolve():
            report.errors.append(
                f"cannot move {item.old_id}: destination already exists ({item.new_dir})"
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
            report.errors.append(f"{item.old_id}: {exc}")

    if _rewrite_sidecar(library_root / ANNOTATIONS_FILENAME, mapping, dry_run):
        report.rewritten_files.append(ANNOTATIONS_FILENAME)
    if _rewrite_sidecar(library_root / COMPARISONS_FILENAME, mapping, dry_run):
        report.rewritten_files.append(COMPARISONS_FILENAME)

    return report
