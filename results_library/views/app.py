"""
The explorer: one browser app over one generated data file.

The build writes ``explorer.html`` at the library root and ``explorer/`` next to
it. ``explorer/catalog.js`` holds every result as ``window.CATALOG = {...}``;
the rest of that folder is copied verbatim from ``explorer_assets/``. A script
tag is used instead of ``fetch`` because browsers refuse ``fetch`` over
``file://``, and the library is opened straight from the synced folder.

Python decides everything that needs a rule or the library on disk: which
result heads each family, the links into bundles and ``sources/``, the LaTeX
strings. The browser only groups, filters, and draws.

Rebuilt from scratch every time, like the classic site.
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd

from results_library.comparisons import load_comparisons
from results_library.views.latex import latex_table, tsv_table
from results_library.views.site import (
    _IMAGE_SUFFIXES,
    _PROVENANCE_FIELDS,
    _PROVENANCE_HINTS,
    _clean,
    _cohort_key,
    _data_selection_rows,
    _extract_is_distinct_dump,
    _format_number,
    _library_files,
    _ordered_plot_stems,
    _plot_caption,
    _provenance_href,
    _split_joined,
    _stat_fields,
    _strip_dollars,
)
from results_schema.nuclides import nucleus_sort_key, parse_nuclide
from results_schema.slugs import normalize_lineage

EXPLORER_PAGE = "explorer.html"
EXPLORER_DIRNAME = "explorer"
DATA_FILENAME = "catalog.js"

#: Which selection set heads a family when nothing is pinned, best first.
#: ``final`` is the modern pipeline's own choice; legacy captures never made a
#: ``final`` set, so their filters are ranked here instead. Sets not listed
#: rank after these, alphabetically.
HEADLINE_SELECTION_ORDER: tuple[str, ...] = (
    "final",
    "19_convVP_loss_straight_ns",
    "23_loss_straight_ns",
    "10_loss_vp_straight_nsigma",
    "all_models",
)

_STATUS_RANK = {"published": 0, "working": 1, "probing": 2, "superseded": 3}

#: The home page's results matrix: groups of columns, each column the
#: observables it holds (the first one names the column). Observables no column
#: lists fall into the last group's catch-all column (``None``), ordered by
#: :data:`_OTHER_ORDER`. A library shows only the columns it has results for.
MATRIX_GROUPS: tuple[tuple[str, tuple[tuple[str, Optional[tuple[str, ...]]], ...]], ...] = (
    ("Energies", (("Eabs", ("Eabs", "E")), ("Eexc", ("Eexc",)), ("Ethr", ("Ethr",)), ("Erel", ("Erel",)))),
    ("Radii", (("rp", ("rp",)), ("rpp", ("rpp",)), ("BSR", ("BSR", "BSR (from rp, rpp)")))),
    ("Other", (("other", None),)),
)
_OTHER_ORDER = ("B(E2)", "|Qp|", "|Qn|", "Mp", "Mn", "Mn/Mp", "MnQp/MpQn", "B(E2)/Qp^2")

#: Catalog columns copied into the data file as they are.
_ROW_FIELDS = (
    "id", "family", "nucleus", "nucleus_label", "state_label", "observable", "observable_label",
    "units", "potential", "selection_set", "run_datetime", "run_date_label",
    "value_label", "median", "err_low", "err_high", "N_models", "status", "title",
    "note", "outcome", "reference_nucleus", "reference_convention", "subject_kind",
    "lr_schedule_label", "lr_schedule_detail",
)


def _selection_rank(name: Any) -> tuple[int, str]:
    text = str(name or "")
    try:
        return (HEADLINE_SELECTION_ORDER.index(text), text)
    except ValueError:
        return (len(HEADLINE_SELECTION_ORDER), text)


def headline_ids(rows: Iterable[Mapping[str, Any]], *, per_potential: bool = False) -> set[str]:
    """The one result that heads each family, per lineage.

    A result annotated ``headline = true`` wins. Otherwise the order is:
    curation status (published first), then :data:`HEADLINE_SELECTION_ORDER`,
    then the newest run. When several results in a family are pinned, the
    same order breaks the tie. With ``per_potential``, each potential within a
    family gets its own head, for views filtered to one potential.
    """
    groups: Dict[tuple[str, ...], List[Mapping[str, Any]]] = {}
    for row in rows:
        key = (normalize_lineage(row.get("lineage")), str(row.get("family") or ""))
        if per_potential:
            key += (str(row.get("potential") or ""),)
        groups.setdefault(key, []).append(row)

    def order(row: Mapping[str, Any]) -> tuple:
        return (
            0 if row.get("headline") is True else 1,
            _STATUS_RANK.get(str(row.get("status") or "probing"), 9),
            _selection_rank(row.get("selection_set")),
        )

    def newest_first(group: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
        return sorted(
            group,
            key=lambda row: (str(row.get("run_datetime") or ""), str(row.get("id") or "")),
            reverse=True,
        )

    # ``min`` keeps the first of equal keys, so ties go to the newest run.
    return {str(min(newest_first(group), key=order).get("id")) for group in groups.values()}


def _number(value: Any) -> Optional[float]:
    value = _clean(value)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


#: Paths inside a result's own bundle are stored as ``@/<name>`` to keep the
#: data file small; the explorer joins them back onto ``bundle``.
_IN_BUNDLE = "@/"


def _short(path: Optional[str], bundle: str) -> Optional[str]:
    if not path:
        return None
    text = str(path).replace("\\", "/")
    prefix = bundle.rstrip("/") + "/"
    return _IN_BUNDLE + text[len(prefix):] if bundle and text.startswith(prefix) else text


def _plots(row: Mapping[str, Any]) -> List[Dict[str, Any]]:
    by_key = {
        key[len("artifact_"):]: str(value)
        for key, value in row.items()
        if key.startswith("artifact_") and _clean(value)
    }
    stems = [key[: -len("_plot")] for key in by_key if key.endswith("_plot")]
    bundle = str(row.get("bundle_path") or "")
    plots = []
    for stem in _ordered_plot_stems(row, stems):
        target = by_key[f"{stem}_plot"]
        plots.append(
            {
                "caption": _plot_caption(stem),
                "href": _short(target, bundle),
                "image": Path(target).suffix.lower() in _IMAGE_SUFFIXES,
                "csv": _short(by_key.get(f"{stem}_data_csv"), bundle),
            }
        )
    return plots


def _files(row: Mapping[str, Any]) -> List[Dict[str, str]]:
    bundle = str(row.get("bundle_path") or "")
    files = [{"name": "bundle folder", "label": "", "href": bundle}]
    # ``_library_files`` builds links relative to a page; the explorer page sits
    # at the library root, so a root-level page path keeps them as they are.
    files.extend(_library_files(row, EXPLORER_PAGE))
    for key, value in sorted(row.items()):
        if key.startswith("artifact_") and _clean(value):
            files.append(
                {"name": Path(str(value)).name, "label": key[len("artifact_"):], "href": _short(str(value), bundle)}
            )
    return files


def _provenance(row: Mapping[str, Any]) -> List[List[Any]]:
    items = []
    for key, label in _PROVENANCE_FIELDS:
        if key == "source_file_path" and not _extract_is_distinct_dump(row):
            continue
        value = row.get(key)
        if value in (None, ""):
            continue
        link = _provenance_href(row, key, EXPLORER_PAGE)
        items.append([label, str(value), link] if link else [label, str(value)])
    return items


def _hints() -> Dict[str, str]:
    """Field explanations by label, shared by every row."""
    hints = {label: hint for _key, label, _latex, hint in _stat_fields() if hint}
    labels = dict(_PROVENANCE_FIELDS)
    hints.update({labels[key]: hint for key, hint in _PROVENANCE_HINTS.items() if key in labels})
    sample = {"nmax_range": "x", "homega_range": "x", "minimum_filter_enabled": True}
    hints.update({label: hint for label, _latex, _value, hint in _data_selection_rows(sample) if hint})
    return hints


def _label_tex() -> Dict[str, str]:
    """KaTeX source for labels that carry math (Nmax, ħΩ), keyed by the Unicode label."""
    found = {label: latex for _key, label, latex, _hint in _stat_fields() if latex}
    sample = {"nmax_range": "x", "homega_range": "x"}
    found.update({label: latex for label, latex, _value, _hint in _data_selection_rows(sample) if latex})
    return found


def _axes() -> Dict[str, Dict[str, str]]:
    """The training-window axes, as the classic site labels them."""
    from results_schema.labels import axis_latex, axis_unicode

    return {
        axis: {"latex": axis_latex(axis, wrap=False), "label": axis_unicode(axis)}
        for axis in ("Nmax", "hOmega")
    }


def _nucleus_coordinates(nucleus: str) -> Optional[Dict[str, int]]:
    try:
        nuclide = parse_nuclide(nucleus)
    except ValueError:
        return None
    return {"Z": nuclide.Z, "N": nuclide.N, "A": nuclide.A, "symbol": nuclide.element}


def _level(row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """A state's quantum numbers (2J, parity, 2T, index), for level schemes."""
    if str(row.get("subject_kind") or "") != "state":
        return None
    level = {key: _number(row.get(field)) for key, field in (("J2", "J2"), ("T2", "T2"), ("n", "index"))}
    parity = _clean(row.get("parity"))
    if level["J2"] is None or parity not in ("+", "-"):
        return None
    level["parity"] = parity
    return level


def matrix_columns(records: Iterable[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """The results-matrix columns each lineage has results for, per :data:`MATRIX_GROUPS`."""
    present: Dict[str, Dict[str, Mapping[str, Any]]] = {}
    for row in records:
        observable = _clean(row.get("observable"))
        if observable is not None:
            present.setdefault(normalize_lineage(row.get("lineage")), {}).setdefault(str(observable), row)
    listed = {name for _group, columns in MATRIX_GROUPS for _key, names in columns for name in names or ()}

    def rank(name: str) -> tuple:
        return (_OTHER_ORDER.index(name) if name in _OTHER_ORDER else len(_OTHER_ORDER), name)

    out: Dict[str, List[Dict[str, Any]]] = {}
    for lineage, seen in present.items():
        columns = []
        for group, specs in MATRIX_GROUPS:
            for key, names in specs:
                held = [n for n in names if n in seen] if names else sorted((n for n in seen if n not in listed), key=rank)
                if not held:
                    continue
                first = seen[held[0]]
                column = {"key": key, "group": group, "observables": held}
                if names:
                    column["latex"] = _strip_dollars(first.get("observable_latex"))
                    column["label"] = _clean(first.get("observable_label")) or held[0]
                    column["units"] = _clean(first.get("units")) or ""
                else:
                    column["label"] = "E2 and moments" if set(held) <= set(_OTHER_ORDER) else "Other observables"
                    column["units"] = ""
                columns.append(column)
        out[lineage] = columns
    return out


def export_row(
    row: Mapping[str, Any],
    *,
    headline: bool,
    papers: Sequence[Mapping[str, Any]] = (),
) -> Dict[str, Any]:
    """One result as the explorer reads it."""
    out: Dict[str, Any] = {key: _clean(row.get(key)) for key in _ROW_FIELDS}
    for key in ("median", "err_low", "err_high", "N_models"):
        out[key] = _number(row.get(key))
    out["lineage"] = normalize_lineage(row.get("lineage"))
    out["status"] = out.get("status") or "probing"
    out["state_latex"] = _strip_dollars(row.get("state_latex"))
    out["observable_latex"] = _strip_dollars(row.get("observable_latex"))
    out["value_latex"] = _strip_dollars(row.get("value_latex"))
    out["level"] = _level(row)
    out["nmax"] = [_number(row.get("bounds_Nmax_min")), _number(row.get("bounds_Nmax_max"))]
    out["homega"] = [_number(row.get("bounds_hOmega_min")), _number(row.get("bounds_hOmega_max"))]
    out["bundle"] = str(row.get("bundle_path") or "")
    out["tags"] = _split_joined(row.get("tags"))
    out["headline"] = bool(headline)
    out["pinned"] = row.get("headline") is True
    out["papers"] = [
        {"id": str(p.get("id")), "title": str(p.get("title") or p.get("id")), "href": str(p.get("href") or "")}
        for p in papers
    ]
    out["plots"] = _plots(row)
    out["files"] = _files(row)
    out["stats"] = [
        [label, _format_number(row.get(key))]
        for key, label, _latex, _hint in _stat_fields()
        if _clean(row.get(key)) is not None
    ]
    out["selection"] = [[label, value] for label, _latex, value, _hint in _data_selection_rows(row)]
    out["provenance"] = _provenance(row)
    out["latex"] = latex_table([row])
    out["tsv"] = tsv_table([row])
    return out


def explorer_data(
    library_root: Path,
    catalog: pd.DataFrame,
    *,
    paper_links: Optional[Mapping[str, List[Mapping[str, Any]]]] = None,
    papers: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Everything ``catalog.js`` carries, as plain JSON-ready data.

    ``papers`` is the paper storage's own view (``paper_storage.views.explorer``),
    passed through untouched; this package does not read papers itself.
    """
    records = [
        {key: _clean(value) for key, value in record.items()}
        for record in catalog.to_dict("records")
    ]
    heads = headline_ids(records)
    potential_heads = headline_ids(records, per_potential=True)
    links = {str(k): list(v) for k, v in (paper_links or {}).items()}
    # One trained ensemble (same run, family, potential, bounds), numbered so
    # the long key is not repeated on every row.
    ensembles: Dict[str, int] = {}
    rows = []
    for record in records:
        row = export_row(record, headline=str(record.get("id")) in heads, papers=links.get(str(record.get("id")), ()))
        row["potential_headline"] = str(record.get("id")) in potential_heads
        row["ensemble"] = ensembles.setdefault(_cohort_key(record), len(ensembles))
        rows.append(row)
    rows.sort(key=lambda r: (nucleus_sort_key(r.get("nucleus") or ""), str(r.get("family")), str(r.get("id"))))

    nuclei = {}
    for row in rows:
        name = str(row.get("nucleus") or "")
        if name and name not in nuclei:
            nuclei[name] = {
                "label": row.get("nucleus_label") or name,
                "order": list(nucleus_sort_key(name)[:3]),
                "chart": _nucleus_coordinates(name),
            }

    figures = [
        {
            "title": figure.title,
            "caption": figure.caption,
            "href": figure.file,
            "image": Path(figure.file).suffix.lower() in _IMAGE_SUFFIXES,
            "results": list(figure.results),
        }
        for figure in load_comparisons(library_root)
    ]

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "headline_order": list(HEADLINE_SELECTION_ORDER),
        "with_papers": paper_links is not None,
        "papers": dict(papers) if papers is not None else None,
        "hints": _hints(),
        "label_tex": _label_tex(),
        "axes": _axes(),
        "nuclei": nuclei,
        "matrix": matrix_columns(records),
        "figures": figures,
        "rows": rows,
    }


def _copy_tree(source: Path, target: Path) -> None:
    files = [path for path in sorted(source.rglob("*")) if path.is_file()]
    last_error: Optional[OSError] = None
    for attempt in range(6):
        try:
            # Drive can finish deleting the old folder after it is recreated.
            target.mkdir(parents=True, exist_ok=True)
            for item in files:
                dest = target / item.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(item.read_bytes())
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"Could not copy explorer assets to {target}") from last_error


def build_explorer(
    library_root: Path,
    catalog: Optional[pd.DataFrame] = None,
    *,
    paper_links: Optional[Mapping[str, List[Mapping[str, Any]]]] = None,
    papers: Optional[Mapping[str, Any]] = None,
) -> Path:
    """Write ``explorer.html`` and ``explorer/`` and return the page path."""
    library_root = Path(library_root)
    if catalog is None:
        from results_library.catalog import load_catalog

        catalog = load_catalog(library_root)

    here = Path(__file__).parent
    target = library_root / EXPLORER_DIRNAME
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    assets = here / "explorer_assets"
    _copy_tree(assets / "app", target)
    _copy_tree(here / "assets" / "katex", target / "katex")

    data = explorer_data(library_root, catalog, paper_links=paper_links, papers=papers)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # A stray "</script>" inside a note would end an inline script; the data
    # file is loaded by src, but escape it anyway so the file stays inert.
    payload = payload.replace("</", "<\\/")
    (target / DATA_FILENAME).write_text(f"window.CATALOG = {payload};\n", encoding="utf-8")

    page = library_root / EXPLORER_PAGE
    page.write_bytes((assets / EXPLORER_PAGE).read_bytes())
    return page
