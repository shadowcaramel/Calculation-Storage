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

logger = logging.getLogger(__name__)

SITE_DIRNAME = "site"
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
            "setup_label", "potential", "run_date_label",
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

        self._write_exports(rows)
        self._render_index(environment, rows, figures, rows_by_id)
        self._render_nucleus_pages(environment, rows, figures, rows_by_id)
        self._render_result_pages(environment, rows, figures, rows_by_id)
        if figures:
            self._render_comparisons(environment, rows, figures, rows_by_id)

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

    def _write_exports(self, rows: List[Dict[str, Any]]) -> None:
        """Downloadable table exports, generated from catalog values."""
        exports_dir = self.site_root / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        groups: Dict[str, List[Dict[str, Any]]] = {"all": _main_table_rows(rows)}
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

    def _index_context(
        self,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
        *,
        root: str,
        page_path: str,
    ) -> Dict[str, Any]:
        table_rows = _main_table_rows(rows)
        counts: Dict[str, int] = {}
        labels: Dict[str, str] = {}
        for row in table_rows:
            nucleus = str(row.get("nucleus") or "")
            counts[nucleus] = counts.get(nucleus, 0) + 1
            labels.setdefault(nucleus, str(row.get("nucleus_label") or nucleus))

        nuclei = [
            {"slug": _nucleus_slug(n), "label": labels[n], "count": counts[n]}
            for n in sorted(counts, key=nucleus_sort_key)
        ]
        return {
            "root": root,
            "rows": table_rows,
            "nuclei": nuclei,
            "statuses": STATUSES,
            "hide_probing": _hide_probing_default(table_rows),
            "exports": _exports(table_rows),
            "generated_at": self.generated_at,
            "record_count": len(rows),
            "comparison_figures": _figure_views(figures, page_path, rows_by_id),
        }

    def _render_index(
        self,
        environment,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
    ) -> None:
        template = environment.get_template("index.html")
        # Nested copy: asset and page links are same-folder (`assets/…`).
        self._render(
            self.site_root / "index.html",
            template,
            **self._index_context(
                rows,
                figures,
                rows_by_id,
                root="",
                page_path=f"{SITE_DIRNAME}/index.html",
            ),
        )
        # Library-root copy: a real HTML file, not a shortcut, so the browser
        # still finds CSS/JS/KaTeX under site/. Drive and Windows shortcuts
        # resolve relative URLs against the shortcut's folder and come up empty.
        self._render(
            self.library_root / "index.html",
            template,
            **self._index_context(
                rows,
                figures,
                rows_by_id,
                root=f"{SITE_DIRNAME}/",
                page_path="index.html",
            ),
        )

    def _render_nucleus_pages(
        self,
        environment,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
    ) -> None:
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
                        "heading_latex": state_rows[0].get("state_latex"),
                        "table_id": f"{_nucleus_slug(nucleus)}-{state_slug}".replace(
                            "--to--", "-to-"
                        ),
                        "rows": state_rows,
                        "exports": _exports(state_rows),
                    }
                )

            page_path = f"{SITE_DIRNAME}/nucleus/{_nucleus_slug(nucleus)}.html"
            tabs = _selection_tabs(nucleus_rows)
            self._render(
                self.site_root / "nucleus" / f"{_nucleus_slug(nucleus)}.html",
                template,
                root="../",
                nucleus=nucleus,
                nucleus_label=nucleus_rows[0].get("nucleus_label") or nucleus,
                groups=groups,
                statuses=STATUSES,
                hide_probing=_hide_probing_default(nucleus_rows),
                generated_at=self.generated_at,
                record_count=len(nucleus_rows),
                selection_tabs=tabs,
                default_selection=tabs[0] if tabs else None,
                comparison_figures=_figure_views(
                    figures_for_nucleus(figures, nucleus), page_path, rows_by_id
                ),
            )

    def _render_result_pages(
        self,
        environment,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
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

            plots, artifacts = self._collect_artifacts(row, page_path)
            stats = [
                (label, latex, _format_number(row.get(key)), hint)
                for key, label, latex, hint in _stat_fields()
                if row.get(key) is not None
            ]
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
                generated_at=self.generated_at,
                record_count=1,
            )

    def _render_comparisons(
        self,
        environment,
        rows: List[Dict[str, Any]],
        figures: List[ComparisonFigure],
        rows_by_id: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self._render(
            self.site_root / "comparisons.html",
            environment.get_template("comparisons.html"),
            root="",
            comparison_figures=_figure_views(
                figures, f"{SITE_DIRNAME}/comparisons.html", rows_by_id
            ),
            generated_at=self.generated_at,
            record_count=len(rows),
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
