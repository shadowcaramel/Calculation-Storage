"""
Catalog builder: one table describing every stored result.

Scans ``bundles/**/result.json``, upgrades old records on read, merges the
hand-edited annotations, and writes ``catalog.parquet`` (for analysis in pandas)
and ``catalog.db`` (for SQL and Datasette).

The build is a pure function of the bundles plus the annotations and **always
runs from scratch**. There is no incremental state to corrupt, so the catalog can
be deleted and rebuilt at any time; at a few thousand records this takes seconds.

Records are read as plain dictionaries rather than validated models, so a single
malformed bundle is reported by the lint pass instead of aborting the build.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from results_library.annotations import load_annotations, merge_annotation
from results_library.migrations import apply_migrations

logger = logging.getLogger(__name__)

BUNDLES_DIRNAME = "bundles"
CATALOG_PARQUET = "catalog.parquet"
CATALOG_DB = "catalog.db"
CATALOG_TABLE = "results"

#: List-valued fields are joined for storage, because SQLite has no array type
#: and a single string keeps the parquet and SQLite views identical.
LIST_SEPARATOR = "; "


@dataclass
class ScannedRecord:
    """One record as read from disk, before flattening."""

    path: Path
    data: Dict[str, Any]
    migrations_applied: List[str] = field(default_factory=list)

    @property
    def bundle_dir(self) -> Path:
        return self.path.parent

    @property
    def result_id(self) -> str:
        return str(self.data.get("id", ""))


@dataclass
class ScanResult:
    records: List[ScannedRecord] = field(default_factory=list)
    unreadable: List[str] = field(default_factory=list)


def scan_bundles(library_root: Path) -> ScanResult:
    """Read every ``result.json`` under ``bundles/``, applying migrations."""
    root = Path(library_root) / BUNDLES_DIRNAME
    result = ScanResult()

    if not root.exists():
        logger.warning("No bundles directory at %s", root)
        return result

    for path in sorted(root.rglob("result.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.unreadable.append(f"{path}: {exc}")
            continue

        if not isinstance(data, dict):
            result.unreadable.append(f"{path}: expected a JSON object")
            continue

        data, applied = apply_migrations(data)
        result.records.append(
            ScannedRecord(path=path, data=data, migrations_applied=applied)
        )

    return result


# ---------------------------------------------------------------------------
# Flattening
# ---------------------------------------------------------------------------

def _state_columns(state: Optional[Dict[str, Any]], prefix: str) -> Dict[str, Any]:
    if not state:
        return {}
    return {
        f"{prefix}J2": state.get("J2"),
        f"{prefix}parity": state.get("parity"),
        f"{prefix}T2": state.get("T2"),
        f"{prefix}index": state.get("index"),
    }


def _display_labels(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build display labels from the identity.

    Rendered here, once, so a paper table and the web page can never disagree
    about how a state or a value is written.
    """
    from results_schema.labels import (
        format_value_with_uncertainty,
        nuclide_unicode,
        subject_latex,
        subject_unicode,
    )

    subject = record.get("subject") or {}
    computed = record.get("computed") or {}
    labels: Dict[str, Any] = {}

    try:
        nucleus = record["id"].split("/")[0]
        labels["nucleus_label"] = nuclide_unicode(nucleus)
    except Exception:
        labels["nucleus_label"] = None

    try:
        labels["state_label"] = subject_unicode(subject)
        labels["state_latex"] = subject_latex(subject)
    except Exception:
        labels["state_label"] = None
        labels["state_latex"] = None

    median = computed.get("median")
    err_low = computed.get("err_low")
    err_high = computed.get("err_high")
    if median is not None and err_low is not None and err_high is not None:
        labels["value_latex"] = format_value_with_uncertainty(
            float(median), float(err_low), float(err_high)
        )
        labels["value_label"] = (
            f"{float(median):.3f} +{float(err_high):.3f} / -{float(err_low):.3f}"
        )
    elif median is not None:
        labels["value_latex"] = f"{float(median):.3f}"
        labels["value_label"] = f"{float(median):.3f}"
    else:
        labels["value_latex"] = None
        labels["value_label"] = None

    return labels


def flatten_record(
    scanned: ScannedRecord,
    library_root: Path,
    annotations: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Turn one record into a single flat catalog row."""
    from results_schema.labels import observable_unicode, setup_label

    record = scanned.data
    subject = record.get("subject") or {}
    observable = record.get("observable") or {}
    computed = record.get("computed") or {}
    variant = record.get("variant") or {}
    provenance = record.get("provenance") or {}
    reference = record.get("reference") or {}
    artifacts = record.get("artifacts") or {}

    result_id = str(record.get("id", ""))
    segments = result_id.split("/")

    row: Dict[str, Any] = {
        "id": result_id,
        "family": record.get("family"),
        "schema_version": record.get("schema_version"),
        "nucleus": segments[0] if segments else None,
        "state_slug": segments[1] if len(segments) > 1 else None,
        "observable_slug": segments[2] if len(segments) > 2 else None,
        "run_stamp": segments[3] if len(segments) > 3 else None,
        "subject_kind": subject.get("kind"),
        "observable": observable.get("name") or observable.get("slug"),
        "observable_latex": observable.get("latex"),
        "observable_label": observable_unicode(
            observable.get("name") or observable.get("slug"),
            stored=observable.get("unicode"),
            column_labels=record.get("column_labels"),
        ),
        "units": observable.get("units"),
        "direction": observable.get("direction"),
    }

    if subject.get("kind") == "transition":
        row.update(_state_columns((subject.get("initial") or {}).get("state"), "initial_"))
        row.update(_state_columns((subject.get("final") or {}).get("state"), "final_"))
        row.update(_state_columns((subject.get("initial") or {}).get("state"), ""))
    else:
        row.update(_state_columns(subject.get("state"), ""))

    # Statistics
    for key in (
        "median", "Q1", "Q3", "err_low", "err_high", "IQR", "N_models",
        "Nmax_final", "uncertainty_method", "homega_aggregation",
        "KDE_mode", "HDR_low", "HDR_high",
    ):
        row[key] = computed.get(key)

    # Variant / setup
    row["selection_set"] = variant.get("selection_set")
    row["variant_hash"] = variant.get("variant_hash")
    row["config_name"] = variant.get("config_name")
    row["filter_criteria"] = LIST_SEPARATOR.join(variant.get("filter_criteria") or [])
    for column, limits in (variant.get("bounds") or {}).items():
        if isinstance(limits, (list, tuple)) and len(limits) == 2:
            row[f"bounds_{column}_min"] = limits[0]
            row[f"bounds_{column}_max"] = limits[1]
    row["setup_label"] = setup_label(
        variant.get("bounds") or {}, record.get("column_labels")
    )

    # Reference
    row["reference_nucleus"] = reference.get("nucleus")
    row["reference_alias"] = reference.get("alias")
    row["reference_convention"] = LIST_SEPARATOR.join(
        f"{k}={v}" for k, v in sorted((reference.get("convention") or {}).items())
    )

    # Provenance
    for key in (
        "code_version", "created_at", "run_dir", "config_snapshot",
        "source_workbook", "source_sheet",
    ):
        row[key] = provenance.get(key)

    # Human layer wins over the record's default status.
    row.update(merge_annotation(record, annotations.get(result_id, {})))
    row["tags"] = LIST_SEPARATOR.join(row.get("tags") or [])

    # Artifacts, as paths relative to the library root so the site and the Excel
    # view can link to them from anywhere the library is synced.
    bundle_rel = scanned.bundle_dir.relative_to(Path(library_root)).as_posix()
    row["bundle_path"] = bundle_rel
    row["available"] = LIST_SEPARATOR.join(record.get("available") or [])
    for key, filename in artifacts.items():
        row[f"artifact_{key}"] = f"{bundle_rel}/{filename}"

    row["migrations_applied"] = LIST_SEPARATOR.join(scanned.migrations_applied)
    row.update(_display_labels(record))
    return row


def build_catalog(library_root: Path) -> tuple[pd.DataFrame, ScanResult]:
    """Scan the library and return the catalog table plus the raw scan."""
    library_root = Path(library_root)
    scan = scan_bundles(library_root)
    annotations = load_annotations(library_root)

    rows = [flatten_record(record, library_root, annotations) for record in scan.records]
    frame = pd.DataFrame(rows)

    if not frame.empty:
        # Newest first, which is what you want when opening the catalog to see
        # what just finished.
        sort_columns = [c for c in ("nucleus", "family", "run_stamp") if c in frame]
        if sort_columns:
            frame = frame.sort_values(sort_columns, ascending=[True, True, False])
        frame = frame.reset_index(drop=True)

    return frame, scan


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_parquet(frame: pd.DataFrame, library_root: Path) -> Path:
    path = Path(library_root) / CATALOG_PARQUET
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame
    if out.empty and len(out.columns) == 0:
        # pyarrow cannot write a completely schemaless empty frame
        out = pd.DataFrame({"id": pd.Series(dtype="string")})
    out.to_parquet(path, index=False)
    return path


def write_sqlite(frame: pd.DataFrame, library_root: Path) -> Path:
    """Write ``catalog.db`` for SQL queries and Datasette.

    Rewritten wholesale each build, matching the from-scratch policy.
    """
    path = Path(library_root) / CATALOG_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    with sqlite3.connect(path) as connection:
        if frame.empty:
            connection.execute(
                f"CREATE TABLE {CATALOG_TABLE} (id TEXT PRIMARY KEY)"
            )
        else:
            frame.to_sql(CATALOG_TABLE, connection, index=False)
            # Duplicates are a lint error, not a build failure: the catalog
            # must still write so the rest of the views can be inspected.
            try:
                connection.execute(
                    f"CREATE UNIQUE INDEX idx_results_id ON {CATALOG_TABLE}(id)"
                )
            except sqlite3.Error:
                logger.warning(
                    "Could not create a unique index on results.id "
                    "(duplicate ids?). Run lint for details."
                )
            for column in ("family", "nucleus", "observable", "status"):
                if column in frame.columns:
                    connection.execute(
                        f"CREATE INDEX idx_results_{column} "
                        f"ON {CATALOG_TABLE}({column})"
                    )
    return path


def write_catalog(frame: pd.DataFrame, library_root: Path) -> Dict[str, Path]:
    """Write both catalog forms and return their paths."""
    return {
        "parquet": write_parquet(frame, library_root),
        "sqlite": write_sqlite(frame, library_root),
    }


def load_catalog(library_root: Path) -> pd.DataFrame:
    """Read a previously built catalog, for views and analysis."""
    path = Path(library_root) / CATALOG_PARQUET
    if not path.exists():
        raise FileNotFoundError(
            f"No catalog at {path}. Build it first: "
            f"python -m results_library.cli catalog --library <path>"
        )
    return pd.read_parquet(path)
