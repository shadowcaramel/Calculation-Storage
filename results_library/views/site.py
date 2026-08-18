"""
Static HTML site generated from the catalog.

Plain files, no server: the site is meant to be opened straight from the synced
library folder, so every link is relative and there are no network dependencies.
Filtering, sorting, and copy-to-clipboard run client-side.

Rebuilt from scratch every time. The site is a view, never a source of truth, so
deleting it costs nothing.
"""

from __future__ import annotations

import logging
import posixpath
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd

from results_library.annotations import STATUSES
from results_library.views.latex import (
    DEFAULT_COLUMNS,
    csv_table,
    latex_table,
    tsv_table,
)

logger = logging.getLogger(__name__)

SITE_DIRNAME = "site"
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

#: Columns shown on a detail page, in order, with display names.
_STAT_FIELDS = (
    ("median", "Median (central value)"),
    ("err_low", "Uncertainty low (median - Q1)"),
    ("err_high", "Uncertainty high (Q3 - median)"),
    ("Q1", "Q1"),
    ("Q3", "Q3"),
    ("IQR", "IQR"),
    ("N_models", "Models used"),
    ("Nmax_final", "Nmax final"),
    ("uncertainty_method", "Uncertainty method"),
    ("homega_aggregation", "hOmega aggregation"),
    ("KDE_mode", "KDE mode"),
    ("HDR_low", "HDR low"),
    ("HDR_high", "HDR high"),
)

_PROVENANCE_FIELDS = (
    ("run_stamp", "Run"),
    ("selection_set", "Selection set"),
    ("filter_criteria", "Filter criteria"),
    ("config_name", "Configuration"),
    ("variant_hash", "Variant hash"),
    ("reference_nucleus", "Reference nucleus"),
    ("reference_alias", "Reference state"),
    ("reference_convention", "Reference convention"),
    ("direction", "Transition direction"),
    ("code_version", "Code version"),
    ("created_at", "Captured at"),
    ("run_dir", "Run directory"),
    ("source_workbook", "Source workbook"),
    ("source_sheet", "Source sheet"),
    ("schema_version", "Schema version"),
    ("migrations_applied", "Migrations applied"),
)


def _clean(value: Any) -> Any:
    """Turn pandas NaN/NaT into ``None`` so templates can test truthiness."""
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    if value is pd.NaT:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _page_name(result_id: str) -> str:
    """Flat filename for a detail page, so link depth is always the same."""
    return result_id.replace("/", "__") + ".html"


def _nucleus_slug(nucleus: str) -> str:
    return str(nucleus).replace("/", "_")


def _row_dict(record: Mapping[str, Any]) -> Dict[str, Any]:
    row = {key: _clean(value) for key, value in dict(record).items()}
    row["page"] = _page_name(str(row.get("id", "")))
    row["status"] = row.get("status") or "probing"
    row["search_text"] = " ".join(
        str(row.get(key) or "")
        for key in (
            "nucleus", "nucleus_label", "state_label", "state_slug", "observable",
            "observable_slug", "status", "title", "note", "outcome", "tags",
            "selection_set", "config_name", "run_stamp", "id",
        )
    )
    return row


def _exports(rows: Iterable[Mapping[str, Any]], columns=DEFAULT_COLUMNS) -> Dict[str, str]:
    rows = list(rows)
    return {
        "latex": latex_table(rows, columns),
        "tsv": tsv_table(rows, columns),
        "csv": csv_table(rows, columns),
    }


def _href(from_page: str, to_target: str) -> str:
    """Relative URL from a generated page to a path inside the library.

    ``from_page`` is a file path relative to the library root (for example
    ``site/results/....html``). ``relpath`` treats its start as a directory, so
    the file name has to be stripped or every link gains a spurious ``../``.
    """
    start = posixpath.dirname(from_page.replace("\\", "/")) or "."
    return posixpath.relpath(to_target.replace("\\", "/"), start=start)


def _setup_summary(row: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key, value in row.items():
        if key.startswith("bounds_") and key.endswith("_min"):
            column = key[len("bounds_"): -len("_min")]
            low = _clean(value)
            high = _clean(row.get(f"bounds_{column}_max"))
            if low is not None or high is not None:
                parts.append(f"{column} [{low}, {high}]")
    if row.get("selection_set"):
        parts.append(f"selection {row['selection_set']}")
    return "; ".join(parts)


class SiteBuilder:
    """Renders the catalog into a static site under ``<library>/site``."""

    def __init__(self, library_root: Path, catalog: pd.DataFrame) -> None:
        self.library_root = Path(library_root)
        self.catalog = catalog
        self.site_root = self.library_root / SITE_DIRNAME
        self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # -- environment ---------------------------------------------------

    def _environment(self):
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "Jinja2 is required to build the site. Install the library "
                "requirements: pip install -r requirements.txt"
            ) from exc

        return Environment(
            loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # -- build ---------------------------------------------------------

    def build(self) -> Path:
        """Render the whole site and return its root directory."""
        environment = self._environment()

        if self.site_root.exists():
            shutil.rmtree(self.site_root)
        self.site_root.mkdir(parents=True, exist_ok=True)

        self._copy_assets()

        rows = [_row_dict(record) for record in self.catalog.to_dict("records")]
        rows.sort(key=lambda r: (str(r.get("nucleus") or ""), str(r.get("family") or ""),
                                 str(r.get("run_stamp") or "")))

        self._write_exports(rows)
        self._render_index(environment, rows)
        self._render_nucleus_pages(environment, rows)
        self._render_result_pages(environment, rows)

        return self.site_root

    def _copy_assets(self) -> None:
        source = Path(__file__).parent / "assets"
        target = self.site_root / "assets"
        target.mkdir(parents=True, exist_ok=True)
        for asset in source.iterdir():
            if asset.is_file():
                shutil.copy2(asset, target / asset.name)

    def _write_exports(self, rows: List[Dict[str, Any]]) -> None:
        """Downloadable table exports, generated from catalog values."""
        exports_dir = self.site_root / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        groups: Dict[str, List[Dict[str, Any]]] = {"all": rows}
        for row in rows:
            groups.setdefault(f"nucleus-{_nucleus_slug(row.get('nucleus'))}", []).append(row)

        for table_id, group_rows in groups.items():
            (exports_dir / f"{table_id}.csv").write_text(
                csv_table(group_rows) + "\n", encoding="utf-8"
            )
            (exports_dir / f"{table_id}.tex").write_text(
                latex_table(group_rows) + "\n", encoding="utf-8"
            )

    def _render(self, path: Path, template, **context: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template.render(**context), encoding="utf-8")

    def _render_index(self, environment, rows: List[Dict[str, Any]]) -> None:
        counts: Dict[str, int] = {}
        labels: Dict[str, str] = {}
        for row in rows:
            nucleus = str(row.get("nucleus") or "")
            counts[nucleus] = counts.get(nucleus, 0) + 1
            labels.setdefault(nucleus, str(row.get("nucleus_label") or nucleus))

        nuclei = [
            {"slug": _nucleus_slug(n), "label": labels[n], "count": counts[n]}
            for n in sorted(counts)
        ]

        self._render(
            self.site_root / "index.html",
            environment.get_template("index.html"),
            root="",
            rows=rows,
            nuclei=nuclei,
            statuses=STATUSES,
            exports=_exports(rows),
            generated_at=self.generated_at,
            record_count=len(rows),
        )

    def _render_nucleus_pages(self, environment, rows: List[Dict[str, Any]]) -> None:
        template = environment.get_template("nucleus.html")
        by_nucleus: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            by_nucleus.setdefault(str(row.get("nucleus") or ""), []).append(row)

        for nucleus, nucleus_rows in by_nucleus.items():
            by_state: Dict[str, List[Dict[str, Any]]] = {}
            for row in nucleus_rows:
                by_state.setdefault(str(row.get("state_slug") or ""), []).append(row)

            groups = []
            for state_slug in sorted(by_state):
                state_rows = by_state[state_slug]
                heading = state_rows[0].get("state_label") or state_slug
                groups.append(
                    {
                        "heading": heading,
                        "table_id": f"{_nucleus_slug(nucleus)}-{state_slug}".replace(
                            "--to--", "-to-"
                        ),
                        "rows": state_rows,
                        "exports": _exports(state_rows),
                    }
                )

            self._render(
                self.site_root / "nucleus" / f"{_nucleus_slug(nucleus)}.html",
                template,
                root="../",
                nucleus=nucleus,
                nucleus_label=nucleus_rows[0].get("nucleus_label") or nucleus,
                groups=groups,
                statuses=STATUSES,
                generated_at=self.generated_at,
                record_count=len(nucleus_rows),
            )

    def _render_result_pages(self, environment, rows: List[Dict[str, Any]]) -> None:
        template = environment.get_template("result.html")

        families: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            families.setdefault(str(row.get("family") or ""), []).append(row)

        for row in rows:
            page = row["page"]
            # Detail pages live in site/results/, i.e. two levels below the
            # library root, so links out to bundles resolve from there.
            page_path = f"{SITE_DIRNAME}/results/{page}"

            plots, artifacts = self._collect_artifacts(row, page_path)
            stats = [
                (label, row.get(key))
                for key, label in _STAT_FIELDS
                if row.get(key) is not None
            ]
            provenance = [
                (label, row.get(key))
                for key, label in _PROVENANCE_FIELDS
                if row.get(key) not in (None, "")
            ]

            siblings = sorted(
                families.get(str(row.get("family") or ""), []),
                key=lambda r: str(r.get("run_stamp") or ""),
                reverse=True,
            )
            sibling_rows = [
                {
                    "id": sibling["id"],
                    "page": sibling["page"],
                    "run_stamp": sibling.get("run_stamp"),
                    "setup": _setup_summary(sibling),
                    "value_label": sibling.get("value_label"),
                    "status": sibling.get("status"),
                }
                for sibling in siblings
            ]

            self._render(
                self.site_root / "results" / page,
                template,
                root="../",
                row=row,
                nucleus_slug=_nucleus_slug(row.get("nucleus")),
                plots=plots,
                artifacts=artifacts,
                stats=stats,
                provenance=provenance,
                siblings=sibling_rows if len(sibling_rows) > 1 else [],
                bundle_href=_href(page_path, str(row.get("bundle_path") or "")),
                exports=_exports([row]),
                statuses=STATUSES,
                generated_at=self.generated_at,
                record_count=1,
            )

    def _collect_artifacts(
        self, row: Mapping[str, Any], page_path: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Group artifacts into displayable plots and a flat download list."""
        artifacts: List[Dict[str, Any]] = []
        by_key: Dict[str, str] = {}

        for key, value in row.items():
            if not key.startswith("artifact_") or not value:
                continue
            artifact_key = key[len("artifact_"):]
            by_key[artifact_key] = str(value)
            artifacts.append(
                {
                    "key": artifact_key,
                    "name": Path(str(value)).name,
                    "href": _href(page_path, str(value)),
                }
            )

        plots: List[Dict[str, Any]] = []
        for artifact_key, target in sorted(by_key.items()):
            if not artifact_key.endswith("_plot"):
                continue
            stem = artifact_key[: -len("_plot")]
            data = by_key.get(f"{stem}_data")
            csv_path = by_key.get(f"{stem}_data_csv")
            plots.append(
                {
                    "name": Path(target).name,
                    "href": _href(page_path, target),
                    "is_image": Path(target).suffix.lower() in _IMAGE_SUFFIXES,
                    "data_href": _href(page_path, data) if data else None,
                    "data_name": Path(data).name if data else None,
                    "csv_href": _href(page_path, csv_path) if csv_path else None,
                }
            )

        return plots, sorted(artifacts, key=lambda a: a["key"])


def build_site(library_root: Path, catalog: Optional[pd.DataFrame] = None) -> Path:
    """Build the static site, loading the catalog when not supplied."""
    if catalog is None:
        from results_library.catalog import load_catalog

        catalog = load_catalog(library_root)
    return SiteBuilder(library_root, catalog).build()
