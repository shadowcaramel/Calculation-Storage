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
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd

from results_library.annotations import STATUSES
from results_library.catalog import LIST_SEPARATOR
from results_library.comparisons import (
    ComparisonFigure,
    figures_for_nucleus,
    figures_for_result,
    load_comparisons,
)
from results_library.views.latex import (
    DEFAULT_COLUMNS,
    csv_table,
    latex_table,
    tsv_table,
)
from results_schema.nuclides import nucleus_sort_key
from results_schema.slugs import LINEAGES, normalize_lineage

logger = logging.getLogger(__name__)

SITE_DIRNAME = "site"
LIBRARY_README_NAME = "README.txt"
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

def _stat_fields() -> tuple[tuple[str, str, Optional[str], Optional[str]], ...]:
    """``(catalog key, Unicode label, math label, optional hint)`` for the value table.

    The math form is what KaTeX typesets; the Unicode one stays as the label a
    reader sees before the script runs, and is all Excel and the exports use.
    """
    from results_schema.labels import axis_latex, axis_unicode

    nmax = axis_unicode("Nmax")
    hw = axis_unicode("hOmega")
    nmax_tex = axis_latex("Nmax", wrap=False)
    hw_tex = axis_latex("hOmega", wrap=False)
    return (
        ("median", "Median (central value)", None, None),
        ("err_low", "Uncertainty low (median - Q1)", None, None),
        ("err_high", "Uncertainty high (Q3 - median)", None, None),
        ("Q1", "Q1", None, None),
        ("Q3", "Q3", None, None),
        ("IQR", "IQR", None, None),
        ("N_models", "Models used", None, None),
        ("Nmax_final", f"{nmax} final", rf"{nmax_tex}\ \text{{final}}",
         "Nmax at which the extrapolated value is read off, not the training-data window."),
        ("uncertainty_method", "Uncertainty method", None, None),
        ("homega_aggregation", f"{hw} aggregation", rf"{hw_tex}\ \text{{aggregation}}", None),
        ("KDE_mode", "KDE mode", None, None),
        ("HDR_low", "HDR low", None, None),
        ("HDR_high", "HDR high", None, None),
    )

_PROVENANCE_FIELDS = (
    ("run_stamp", "Run"),
    ("selection_set", "Selection set"),
    ("potential", "Potential"),
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
    ("source_workbook", "Prepared workbook (basename)"),
    ("source_sheet", "Source sheet"),
    ("source_files_name", "Original calculation file(s)"),
    ("source_file_path", "Extracted pivot"),
    ("prepared_file_path", "Prepared data file"),
    ("config_snapshot", "Config snapshot"),
    ("provenance_check_verdict", "S→P check"),
    ("provenance_check_detail", "S→P check detail"),
    ("schema_version", "Schema version"),
    ("migrations_applied", "Migrations applied"),
)

#: Optional muted note under a provenance value. Keys match ``_PROVENANCE_FIELDS``.
_PROVENANCE_HINTS = {
    "variant_hash": (
        "Fingerprint of the setup (bounds, filters, selection, reference "
        "convention), not of this run. Identical setups share it."
    ),
    "source_files_name": (
        "Content-addressed copies of the collaborator MFDn/NCSM dumps, shared "
        "across results that used the same files."
    ),
    "source_file_path": (
        "Content-addressed copy of the extracted pivot workbook used for "
        "conversion, when that file is distinct from the dumps."
    ),
    "prepared_file_path": (
        "Content-addressed copy of the long Excel the pipeline actually read."
    ),
    "config_snapshot": (
        "Frozen config copied into this result's bundle, not the run directory."
    ),
    "provenance_check_verdict": (
        "Numerical check that distinctive values in the prepared workbook "
        "appear in the collaborator dump(s), with each (Nmax, ħΩ, value) "
        "recoverable on a source row or column of one of those files."
    ),
}


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


def _format_number(value: Any) -> str:
    """Readable form of a stored number.

    Records keep full float precision on purpose, but a table showing
    ``1.588239073753357`` is unreadable, and an integral count rendered as
    ``300.0`` looks like a bug. Display rounds to the same three decimals the
    value headline uses; the raw number stays in ``result.json``.
    """
    value = _clean(value)
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:.3f}"
    return str(value)


def _strip_dollars(value: Any) -> str:
    """Bare math body, as KaTeX's ``render`` expects.

    Stored LaTeX is written for a paper, so it usually carries its own ``$``
    delimiters. Those are what the exports need and what KaTeX would try to
    typeset as literal dollar signs.
    """
    value = _clean(value)
    if value is None:
        return ""
    text = str(value).strip()
    while len(text) >= 2 and text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()
    return text


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
            "observable_label", "observable_slug", "status", "title", "note",
            "outcome", "tags", "selection_set", "config_name", "run_stamp", "id",
            "setup_label", "potential", "run_date_label", "nmax_range",
            "homega_range", "lineage",
        )
    )
    row["cohort_key"] = _cohort_key(row)
    row["nmax_scan_key"] = _nmax_scan_key(row)
    return row


def _exports(rows: Iterable[Mapping[str, Any]], columns=DEFAULT_COLUMNS) -> Dict[str, str]:
    rows = list(rows)
    return {
        "latex": latex_table(rows, columns),
        "tsv": tsv_table(rows, columns),
        "csv": csv_table(rows, columns),
    }


def _row_lineage(row: Mapping[str, Any]) -> str:
    return normalize_lineage(row.get("lineage"))


def _split_by_lineage(rows: Iterable[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {name: [] for name in LINEAGES}
    for row in rows:
        groups.setdefault(_row_lineage(row), []).append(dict(row) if not isinstance(row, dict) else row)
    return groups


def _lineage_counts(rows: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    """How many *calculations* sit in each lineage, for the footer.

    Diagnostic selection sets of the same trained ensemble (``all_models``,
    ``conv_*``, …) are not separate calculations; they match the main table,
    which keeps ``final`` plus older records that never declared a set.
    """
    counts = {name: 0 for name in LINEAGES}
    for row in _main_table_rows(rows):
        name = _row_lineage(row)
        counts[name] = counts.get(name, 0) + 1
    return counts


def _nuclei_by_lineage(rows: Iterable[Mapping[str, Any]]) -> Dict[str, set]:
    groups: Dict[str, set] = {name: set() for name in LINEAGES}
    for row in rows:
        nucleus = str(row.get("nucleus") or "")
        if nucleus:
            groups.setdefault(_row_lineage(row), set()).add(nucleus)
    return groups


def _catalogue_filename(lineage: Optional[str]) -> str:
    return "legacy.html" if lineage == "legacy" else "index.html"


def _catalogue_path(lineage: Optional[str], *, at_root: bool) -> str:
    name = _catalogue_filename(lineage)
    return name if at_root else f"{SITE_DIRNAME}/{name}"


def _nucleus_filename(nucleus: str, lineage: str) -> str:
    slug = _nucleus_slug(nucleus)
    return f"{slug}.html" if lineage == "modern" else f"{slug}-legacy.html"


def _nucleus_path(nucleus: str, lineage: str) -> str:
    return f"{SITE_DIRNAME}/nucleus/{_nucleus_filename(nucleus, lineage)}"


def _page_is_library_root(page_path: str) -> bool:
    return not page_path.replace("\\", "/").startswith(f"{SITE_DIRNAME}/")


def _other_lineage(lineage: str) -> str:
    return "legacy" if lineage == "modern" else "modern"


def _href(from_page: str, to_target: str) -> str:
    """Relative URL from a generated page to a path inside the library.

    ``from_page`` is a file path relative to the library root (for example
    ``site/results/....html``). ``relpath`` treats its start as a directory, so
    the file name has to be stripped or every link gains a spurious ``../``.
    """
    start = posixpath.dirname(from_page.replace("\\", "/")) or "."
    return posixpath.relpath(to_target.replace("\\", "/"), start=start)


def _hide_probing_default(rows: Iterable[Mapping[str, Any]]) -> bool:
    """Hide probing rows only once something has been promoted.

    A new library is all ``probing``. Checking the box by default then leaves
    an empty table next to a chip that says there are results, which looks
    broken. Once any result is ``working`` / ``published`` / ``superseded``,
    hide the exploratory ones again so they do not bury the keepers.
    """
    return any((row.get("status") or "probing") != "probing" for row in rows)


_MINIMUM_FILTER_HINT = (
    "At each Nmax, training points on one side of the energy-versus-ħΩ "
    "minimum are kept. Usually on for that state's energy, off for radii "
    "and other observables."
)


def _minimum_filter_value(row: Mapping[str, Any]) -> str:
    """Plain-language On/Off line for the data-selection table."""
    from results_schema.labels import axis_unicode, observable_unicode

    if not row.get("minimum_filter_enabled"):
        return "Off"
    output = row.get("minimum_filter_output")
    obs = observable_unicode(str(output), column_labels=None) if output else "energy"
    independent = axis_unicode(str(row.get("minimum_filter_independent_var") or "hOmega"))
    group = axis_unicode(str(row.get("minimum_filter_group_by") or "Nmax"))
    relation = "≤" if row.get("minimum_filter_keep_direction") == "left" else "≥"
    return f"On — keep {independent} {relation} the {obs} minimum at each {group}"


def _data_selection_rows(
    row: Mapping[str, Any],
) -> List[tuple[str, Optional[str], str, Optional[str]]]:
    """``(Unicode label, math label, value, hint)`` for the detail-page table."""
    from results_schema.labels import axis_latex, axis_unicode

    nmax = axis_unicode("Nmax")
    hw = axis_unicode("hOmega")
    nmax_tex = axis_latex("Nmax", wrap=False)
    hw_tex = axis_latex("hOmega", wrap=False)
    rows: List[tuple[str, Optional[str], str, Optional[str]]] = []
    if row.get("nmax_range"):
        rows.append(
            (
                nmax,
                nmax_tex,
                str(row["nmax_range"]),
                "Training-data window, same as the Nmax column on the index.",
            )
        )
    if row.get("homega_range"):
        rows.append(
            (
                hw,
                hw_tex,
                str(row["homega_range"]),
                "Training-data window for ħΩ.",
            )
        )
    if _clean(row.get("minimum_filter_enabled")) is not None:
        rows.append(
            (
                "Minimum filter",
                None,
                _minimum_filter_value(row),
                _MINIMUM_FILTER_HINT,
            )
        )
    return rows


def _setup_summary(row: Mapping[str, Any]) -> str:
    from results_schema.labels import axis_unicode

    if row.get("setup_label"):
        parts: List[str] = [str(row["setup_label"])]
    else:
        parts = []
        for key, value in row.items():
            if key.startswith("bounds_") and key.endswith("_min"):
                column = key[len("bounds_"): -len("_min")]
                low = _clean(value)
                high = _clean(row.get(f"bounds_{column}_max"))
                if low is not None or high is not None:
                    parts.append(f"{axis_unicode(column)} [{low}, {high}]")
    if row.get("selection_set"):
        parts.append(f"selection {row['selection_set']}")
    return "; ".join(parts)


def _bound_signature(
    row: Mapping[str, Any], skip: frozenset[str] = frozenset()
) -> tuple:
    items = []
    for key, value in row.items():
        text = str(key)
        if not text.startswith("bounds_") or not text.endswith("_min"):
            continue
        column = text[len("bounds_"):-len("_min")]
        if column in skip:
            continue
        items.append((column, _clean(value), _clean(row.get(f"bounds_{column}_max"))))
    return tuple(sorted(items))


def _cohort_key(row: Mapping[str, Any]) -> str:
    """One trained ensemble: same run, family, potential, and training bounds."""
    return "|".join((
        str(row.get("run_dir") or ""),
        str(row.get("family") or ""),
        str(row.get("potential") or ""),
        repr(_bound_signature(row)),
    ))


def _nmax_scan_key(row: Mapping[str, Any]) -> str:
    """Nmax-scan siblings: same family, potential, ħΩ, selection, and filters."""
    return "|".join((
        str(row.get("family") or ""),
        str(row.get("potential") or ""),
        str(row.get("selection_set") or ""),
        str(row.get("filter_criteria") or ""),
        repr(_bound_signature(row, skip=frozenset({"Nmax"}))),
    ))


def _is_main_table_row(row: Mapping[str, Any]) -> bool:
    """Whether a result belongs on the index table.

    Diagnostic selection sets (``all_models``, ``conv_Eexc``, …) stay on
    nucleus and detail pages. The main list is the ``final`` subset, plus
    older records that never declared a selection set.
    """
    name = row.get("selection_set")
    if name is None or str(name).strip() == "":
        return True
    return str(name) == "final"


def _main_table_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if _is_main_table_row(row)]


def _selection_tabs(rows: Iterable[Mapping[str, Any]]) -> List[str]:
    """Selection-set names present in ``rows``, or empty when there is only one."""
    names: List[str] = []
    seen: set[str] = set()
    for row in rows:
        name = row.get("selection_set")
        if not name:
            continue
        name = str(name)
        if name not in seen:
            seen.add(name)
            names.append(name)
    if len(names) < 2:
        return []
    names.sort()
    if "final" in names:
        names.remove("final")
        names.insert(0, "final")
    return names


def _selection_siblings(
    row: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    key = row.get("cohort_key")
    peers = [item for item in rows if item.get("cohort_key") == key]
    names = {item.get("selection_set") for item in peers if item.get("selection_set")}
    if len(names) < 2:
        return []

    def order(item: Mapping[str, Any]) -> tuple:
        name = str(item.get("selection_set") or "")
        return (0 if name == "final" else 1, name)

    return [
        {
            "id": peer["id"],
            "page": peer["page"],
            "selection_set": peer.get("selection_set"),
            "value_label": peer.get("value_label"),
            "value_latex": peer.get("value_latex"),
            "status": peer.get("status"),
        }
        for peer in sorted(peers, key=order)
    ]


def _nmax_windows(
    row: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    key = row.get("nmax_scan_key")
    peers = [item for item in rows if item.get("nmax_scan_key") == key]
    windows = {
        (item.get("bounds_Nmax_min"), item.get("bounds_Nmax_max")) for item in peers
    }
    if len(windows) < 2:
        return []

    def order(item: Mapping[str, Any]) -> tuple:
        high = item.get("bounds_Nmax_max")
        low = item.get("bounds_Nmax_min")
        return (
            high is None,
            high if high is not None else 0,
            low if low is not None else 0,
            str(item.get("run_stamp") or ""),
        )

    return [
        {
            "id": peer["id"],
            "page": peer["page"],
            "nmax_range": peer.get("nmax_range"),
            "run_stamp": peer.get("run_stamp"),
            "setup": _setup_summary(peer),
            "value_label": peer.get("value_label"),
            "value_latex": peer.get("value_latex"),
            "status": peer.get("status"),
        }
        for peer in sorted(peers, key=order)
    ]


def _split_joined(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    return [part for part in str(value).split(LIST_SEPARATOR) if part]


def _extract_is_distinct_dump(row: Mapping[str, Any]) -> bool:
    extract_hash = row.get("source_file_sha256")
    if not extract_hash:
        return bool(row.get("source_file_path"))
    return str(extract_hash) not in _split_joined(row.get("source_files_sha256"))


def _library_files(row: Mapping[str, Any], page_path: str) -> List[Dict[str, str]]:
    files: List[Dict[str, str]] = []
    dump_paths = _split_joined(row.get("source_files_path"))
    dump_names = _split_joined(row.get("source_files_name"))
    for index, path in enumerate(dump_paths):
        name = dump_names[index] if index < len(dump_names) else Path(str(path)).name
        files.append(
            {
                "label": "original calculation file",
                "name": name,
                "href": _href(page_path, str(path)),
            }
        )
    if _extract_is_distinct_dump(row):
        extract_path = row.get("source_file_path")
        if extract_path:
            files.append(
                {
                    "label": "extracted pivot",
                    "name": str(row.get("source_file_name") or Path(str(extract_path)).name),
                    "href": _href(page_path, str(extract_path)),
                }
            )
    prepared_path = row.get("prepared_file_path")
    if prepared_path:
        files.append(
            {
                "label": "prepared workbook",
                "name": str(
                    row.get("prepared_file_name") or Path(str(prepared_path)).name
                ),
                "href": _href(page_path, str(prepared_path)),
            }
        )
    return files


def _provenance_href(row: Mapping[str, Any], key: str, page_path: str) -> Optional[str]:
    if key == "source_files_name":
        paths = _split_joined(row.get("source_files_path"))
        if len(paths) == 1:
            return _href(page_path, paths[0])
        return None
    if key == "source_file_path":
        path = row.get("source_file_path")
        return _href(page_path, str(path)) if path else None
    if key == "prepared_file_path":
        path = row.get("prepared_file_path")
        return _href(page_path, str(path)) if path else None
    if key == "config_snapshot":
        artifact = row.get("artifact_config_snapshot")
        return _href(page_path, str(artifact)) if artifact else None
    return None


def _figure_views(
    figures: Iterable[ComparisonFigure],
    page_path: str,
    rows_by_id: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    views: List[Dict[str, Any]] = []
    for figure in figures:
        views.append(
            {
                "title": figure.title,
                "caption": figure.caption,
                "file": figure.file,
                "href": _href(page_path, figure.file),
                "is_image": Path(figure.file).suffix.lower() in _IMAGE_SUFFIXES,
                "results": [
                    {
                        "id": result_id,
                        "page": _page_name(result_id),
                        "label": (
                            (rows_by_id.get(result_id) or {}).get("value_label")
                            or result_id
                        ),
                    }
                    for result_id in figure.results
                ],
            }
        )
    return views


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

        env = Environment(
            loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        from results_schema.labels import axis_latex, axis_unicode

        env.globals["nmax_label"] = axis_unicode("Nmax")
        env.globals["nmax_latex"] = axis_latex("Nmax", wrap=False)
        env.globals["hw_label"] = axis_unicode("hOmega")
        env.globals["hw_latex"] = axis_latex("hOmega", wrap=False)
        env.filters["num"] = _format_number
        env.filters["strip_dollars"] = _strip_dollars
        return env

    # -- build ---------------------------------------------------------

    def build(self) -> Path:
        """Render the whole site and return its root directory."""
        environment = self._environment()

        if self.site_root.exists():
            shutil.rmtree(self.site_root, ignore_errors=True)
        self.site_root.mkdir(parents=True, exist_ok=True)

        self._copy_assets()
        self._copy_library_readme()

        figures = load_comparisons(self.library_root)
        environment.globals["has_comparisons"] = bool(figures)

        rows = [_row_dict(record) for record in self.catalog.to_dict("records")]
        rows.sort(
            key=lambda r: (
                str(r.get("nucleus") or ""),
                str(r.get("family") or ""),
                str(r.get("id") or ""),
            )
        )
        rows.sort(key=lambda r: str(r.get("run_datetime") or ""), reverse=True)
        rows_by_id = {str(row.get("id") or ""): row for row in rows}
        lineage_counts = _lineage_counts(rows)
        nuclei_by_lineage = _nuclei_by_lineage(rows)

        self._write_exports(rows)
        self._render_index(environment, rows, figures, rows_by_id, lineage_counts)
        self._render_nucleus_pages(
            environment, rows, figures, rows_by_id, lineage_counts, nuclei_by_lineage
        )
        self._render_result_pages(environment, rows, figures, rows_by_id, lineage_counts)
        if figures:
            self._render_comparisons(
                environment, rows, figures, rows_by_id, lineage_counts
            )

        return self.site_root

    def _copy_assets(self) -> None:
        """Copy ``assets/`` into the site, subdirectories included.

        The vendored KaTeX tree lives in ``assets/katex/`` with its own
        ``fonts/``, so the walk has to be recursive: the stylesheet resolves
        fonts relative to itself and a flattened copy would break them.
        """
        source = Path(__file__).parent / "assets"
        target = self.site_root / "assets"
        files = [path for path in sorted(source.rglob("*")) if path.is_file()]

        last_error: Optional[OSError] = None
        for attempt in range(6):
            try:
                # Drive can finish deleting ``site/`` *after* we recreate it.
                target.mkdir(parents=True, exist_ok=True)
                for asset in files:
                    dest = target / asset.relative_to(source)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(asset.read_bytes())
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"Could not copy site assets to {target}") from last_error

    def _copy_library_readme(self) -> None:
        """Copy the short collaborator note to the library root.

        Drive users never clone the git repository, so the site build puts
        ``README.txt`` next to ``index.html``. The git file is the source.
        """
        source = Path(__file__).parent / "library_readme.txt"
        dest = self.library_root / LIBRARY_README_NAME
        dest.write_bytes(source.read_bytes())

    def _write_exports(self, rows: List[Dict[str, Any]]) -> None:
        """Downloadable table exports, generated from catalog values."""
        exports_dir = self.site_root / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        groups: Dict[str, List[Dict[str, Any]]] = {}
        for lineage, lineage_rows in _split_by_lineage(rows).items():
            suffix = "" if lineage == "modern" else "-legacy"
            groups[f"all{suffix}"] = _main_table_rows(lineage_rows)
            for row in lineage_rows:
                key = f"nucleus-{_nucleus_slug(row.get('nucleus'))}{suffix}"
                groups.setdefault(key, []).append(row)

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

    def _page_chrome(
        self,
        *,
        root: str,
        page_path: str,
        lineage: Optional[str],
        lineage_counts: Mapping[str, int],
        record_count: int,
        lineage_modern_href: Optional[str],
        lineage_legacy_href: Optional[str],
        catalog_href: Optional[str] = None,
    ) -> Dict[str, Any]:
        filename = _catalogue_filename(lineage)
        return {
            "root": root,
            "generated_at": self.generated_at,
            "record_count": record_count,
            "lineage": lineage,
            "lineage_counts": dict(lineage_counts),
            "lineage_modern_href": lineage_modern_href,
            "lineage_legacy_href": lineage_legacy_href,
            "catalog_href": catalog_href or f"{root}{filename}",
        }

    def _index_context(
        self,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
        *,
        root: str,
        page_path: str,
        lineage: str,
        lineage_counts: Mapping[str, int],
    ) -> Dict[str, Any]:
        table_rows = _main_table_rows(rows)
        counts: Dict[str, int] = {}
        labels: Dict[str, str] = {}
        for row in table_rows:
            nucleus = str(row.get("nucleus") or "")
            counts[nucleus] = counts.get(nucleus, 0) + 1
            labels.setdefault(nucleus, str(row.get("nucleus_label") or nucleus))

        suffix = "" if lineage == "modern" else "-legacy"
        nuclei = [
            {
                "slug": _nucleus_slug(n),
                "label": labels[n],
                "count": counts[n],
                "href": f"nucleus/{_nucleus_slug(n)}{suffix}.html",
            }
            for n in sorted(counts, key=nucleus_sort_key)
        ]
        at_root = _page_is_library_root(page_path)
        modern_href = (
            None
            if lineage == "modern"
            else _href(page_path, _catalogue_path("modern", at_root=at_root))
        )
        legacy_href = (
            None
            if lineage == "legacy"
            else _href(page_path, _catalogue_path("legacy", at_root=at_root))
        )
        export_id = "all" if lineage == "modern" else "all-legacy"
        context = self._page_chrome(
            root=root,
            page_path=page_path,
            lineage=lineage,
            lineage_counts=lineage_counts,
            record_count=len(rows),
            lineage_modern_href=modern_href,
            lineage_legacy_href=legacy_href,
        )
        context.update(
            {
                "rows": table_rows,
                "nuclei": nuclei,
                "statuses": STATUSES,
                "hide_probing": _hide_probing_default(table_rows),
                "exports": _exports(table_rows),
                "export_id": export_id,
                "comparison_figures": _figure_views(figures, page_path, rows_by_id),
            }
        )
        return context

    def _render_index(
        self,
        environment,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
        lineage_counts: Mapping[str, int],
    ) -> None:
        template = environment.get_template("index.html")
        by_lineage = _split_by_lineage(rows)
        for lineage in LINEAGES:
            lineage_rows = by_lineage.get(lineage) or []
            filename = _catalogue_filename(lineage)
            self._render(
                self.site_root / filename,
                template,
                **self._index_context(
                    lineage_rows,
                    figures,
                    rows_by_id,
                    root="",
                    page_path=f"{SITE_DIRNAME}/{filename}",
                    lineage=lineage,
                    lineage_counts=lineage_counts,
                ),
            )
            # Library-root copy: a real HTML file, not a shortcut, so the browser
            # still finds CSS/JS/KaTeX under site/. Drive and Windows shortcuts
            # resolve relative URLs against the shortcut's folder and come up empty.
            self._render(
                self.library_root / filename,
                template,
                **self._index_context(
                    lineage_rows,
                    figures,
                    rows_by_id,
                    root=f"{SITE_DIRNAME}/",
                    page_path=filename,
                    lineage=lineage,
                    lineage_counts=lineage_counts,
                ),
            )

    def _render_nucleus_pages(
        self,
        environment,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
        lineage_counts: Mapping[str, int],
        nuclei_by_lineage: Mapping[str, set],
    ) -> None:
        template = environment.get_template("nucleus.html")
        by_lineage = _split_by_lineage(rows)
        for lineage, lineage_rows in by_lineage.items():
            by_nucleus: Dict[str, List[Dict[str, Any]]] = {}
            for row in lineage_rows:
                by_nucleus.setdefault(str(row.get("nucleus") or ""), []).append(row)

            suffix = "" if lineage == "modern" else "-legacy"
            other = _other_lineage(lineage)
            for nucleus, nucleus_rows in by_nucleus.items():
                by_state: Dict[str, List[Dict[str, Any]]] = {}
                for row in nucleus_rows:
                    by_state.setdefault(str(row.get("state_slug") or ""), []).append(row)

                groups = []
                for state_slug in sorted(by_state):
                    state_rows = by_state[state_slug]
                    heading = state_rows[0].get("state_label") or state_slug
                    table_id = (
                        f"{_nucleus_slug(nucleus)}-{state_slug}{suffix}".replace(
                            "--to--", "-to-"
                        )
                    )
                    groups.append(
                        {
                            "heading": heading,
                            "heading_latex": state_rows[0].get("state_latex"),
                            "table_id": table_id,
                            "rows": state_rows,
                            "exports": _exports(state_rows),
                        }
                    )

                filename = _nucleus_filename(nucleus, lineage)
                page_path = f"{SITE_DIRNAME}/nucleus/{filename}"
                if nucleus in (nuclei_by_lineage.get(other) or set()):
                    other_target = _nucleus_path(nucleus, other)
                else:
                    other_target = _catalogue_path(other, at_root=False)
                modern_href = (
                    None if lineage == "modern" else _href(page_path, other_target)
                )
                legacy_href = (
                    None if lineage == "legacy" else _href(page_path, other_target)
                )
                tabs = _selection_tabs(nucleus_rows)
                self._render(
                    self.site_root / "nucleus" / filename,
                    template,
                    nucleus=nucleus,
                    nucleus_label=nucleus_rows[0].get("nucleus_label") or nucleus,
                    groups=groups,
                    statuses=STATUSES,
                    hide_probing=_hide_probing_default(nucleus_rows),
                    selection_tabs=tabs,
                    default_selection=tabs[0] if tabs else None,
                    comparison_figures=_figure_views(
                        figures_for_nucleus(figures, nucleus), page_path, rows_by_id
                    ),
                    **self._page_chrome(
                        root="../",
                        page_path=page_path,
                        lineage=lineage,
                        lineage_counts=lineage_counts,
                        record_count=len(nucleus_rows),
                        lineage_modern_href=modern_href,
                        lineage_legacy_href=legacy_href,
                    ),
                )

    def _render_result_pages(
        self,
        environment,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
        lineage_counts: Mapping[str, int],
    ) -> None:
        template = environment.get_template("result.html")

        families: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            families.setdefault(str(row.get("family") or ""), []).append(row)

        for row in rows:
            page = row["page"]
            # Detail pages live in site/results/, i.e. two levels below the
            # library root, so links out to bundles resolve from there.
            page_path = f"{SITE_DIRNAME}/results/{page}"
            lineage = _row_lineage(row)
            nucleus = str(row.get("nucleus") or "")

            plots, artifacts = self._collect_artifacts(row, page_path)
            stats = [
                (label, latex, _format_number(row.get(key)), hint)
                for key, label, latex, hint in _stat_fields()
                if row.get(key) is not None
            ]
            data_selection = _data_selection_rows(row)
            provenance = []
            for key, label in _PROVENANCE_FIELDS:
                if key == "source_file_path" and not _extract_is_distinct_dump(row):
                    continue
                value = row.get(key)
                if value in (None, ""):
                    continue
                provenance.append(
                    (label, value, _PROVENANCE_HINTS.get(key),
                     _provenance_href(row, key, page_path))
                )

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
                    "value_latex": sibling.get("value_latex"),
                    "status": sibling.get("status"),
                }
                for sibling in siblings
            ]

            modern_href = (
                None
                if lineage == "modern"
                else _href(page_path, _catalogue_path("modern", at_root=False))
            )
            legacy_href = (
                None
                if lineage == "legacy"
                else _href(page_path, _catalogue_path("legacy", at_root=False))
            )
            self._render(
                self.site_root / "results" / page,
                template,
                row=row,
                nucleus_slug=_nucleus_slug(nucleus),
                nucleus_href=_href(page_path, _nucleus_path(nucleus, lineage)),
                plots=plots,
                artifacts=artifacts,
                stats=stats,
                data_selection=data_selection,
                provenance=provenance,
                siblings=sibling_rows if len(sibling_rows) > 1 else [],
                selection_siblings=_selection_siblings(row, rows),
                nmax_windows=_nmax_windows(row, rows),
                library_files=_library_files(row, page_path),
                comparison_figures=_figure_views(
                    figures_for_result(figures, str(row.get("id") or "")),
                    page_path,
                    rows_by_id,
                ),
                bundle_href=_href(page_path, str(row.get("bundle_path") or "")),
                exports=_exports([row]),
                statuses=STATUSES,
                **self._page_chrome(
                    root="../",
                    page_path=page_path,
                    lineage=lineage,
                    lineage_counts=lineage_counts,
                    record_count=1,
                    lineage_modern_href=modern_href,
                    lineage_legacy_href=legacy_href,
                ),
            )

    def _render_comparisons(
        self,
        environment,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
        lineage_counts: Mapping[str, int],
    ) -> None:
        page_path = f"{SITE_DIRNAME}/comparisons.html"
        self._render(
            self.site_root / "comparisons.html",
            environment.get_template("comparisons.html"),
            comparison_figures=_figure_views(figures, page_path, rows_by_id),
            **self._page_chrome(
                root="",
                page_path=page_path,
                lineage=None,
                lineage_counts=lineage_counts,
                record_count=len(rows),
                lineage_modern_href=_href(page_path, _catalogue_path("modern", at_root=False)),
                lineage_legacy_href=_href(page_path, _catalogue_path("legacy", at_root=False)),
                catalog_href="index.html",
            ),
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
        plot_stems = [
            key[: -len("_plot")]
            for key in by_key
            if key.endswith("_plot")
        ]
        for stem in _ordered_plot_stems(row, plot_stems):
            target = by_key[f"{stem}_plot"]
            data = by_key.get(f"{stem}_data")
            csv_path = by_key.get(f"{stem}_data_csv")
            plots.append(
                {
                    "name": Path(target).name,
                    "caption": _plot_caption(stem),
                    "href": _href(page_path, target),
                    "is_image": Path(target).suffix.lower() in _IMAGE_SUFFIXES,
                    "data_href": _href(page_path, data) if data else None,
                    "data_name": Path(data).name if data else None,
                    "csv_href": _href(page_path, csv_path) if csv_path else None,
                }
            )

        return plots, sorted(artifacts, key=lambda a: a["key"])


_PLOT_CAPTIONS = {
    "selected_data": "Selected data",
    "legacy_histogram": "Legacy histogram",
    "energy_minima_vs_nmax": "Energy minima vs Nmax",
    "predictions_at_nmax300": "Predictions at Nmax = 300",
}


def _plot_caption(stem: str) -> str:
    """Human label for a captured plot stem, e.g. ``selected_data`` → Selected data."""
    key = str(stem or "")
    if key in _PLOT_CAPTIONS:
        return _PLOT_CAPTIONS[key]
    words = key.replace("_", " ").split()
    if not words:
        return key
    return " ".join([words[0].capitalize(), *words[1:]])


def _available_plot_stems(row: Mapping[str, Any]) -> List[str]:
    raw = row.get("available")
    if isinstance(raw, str):
        return [part for part in raw.split(LIST_SEPARATOR) if part]
    if isinstance(raw, (list, tuple)):
        return [str(part) for part in raw if part]
    return []


def _ordered_plot_stems(row: Mapping[str, Any], stems: Iterable[str]) -> List[str]:
    """``selected_data`` first (quick look), then ``available`` order, then leftovers."""
    present = list(dict.fromkeys(stems))
    ordered: List[str] = []
    if "selected_data" in present:
        ordered.append("selected_data")
    for stem in _available_plot_stems(row):
        if stem in present and stem not in ordered:
            ordered.append(stem)
    for stem in present:
        if stem not in ordered:
            ordered.append(stem)
    return ordered


def build_site(library_root: Path, catalog: Optional[pd.DataFrame] = None) -> Path:
    """Build the static site, loading the catalog when not supplied."""
    if catalog is None:
        from results_library.catalog import load_catalog

        catalog = load_catalog(library_root)
    return SiteBuilder(library_root, catalog).build()
