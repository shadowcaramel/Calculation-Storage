"""
Papers as the explorer reads them.

The explorer sits at the library root, so every path here is library-root
relative (the static paper site under ``paper-site/`` prefixes ``../``
instead). Cells and checks carry the result id they point at; the explorer
turns that into an in-app route. Like the rest of this package, nothing here
imports ``results_library``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from paper_storage.bib import Citation, published_label, published_sort
from paper_storage.lint import PaperIssue
from paper_storage.load import Material, Paper, ParsedGrid, column_index, grid_cell
from paper_storage.numbers import bundle_median, direct_disagrees, format_like_printed
from paper_storage.views.site import (
    _IMAGE_SUFFIXES,
    _cell_math,
    _citation,
    _doi,
    _nuclei,
    _potentials,
    _strip_dollars,
    _title,
)


def explorer_papers(
    library_root: Path,
    papers: Sequence[Paper],
    citations: Optional[Mapping[str, Citation]],
    grids: Mapping[str, ParsedGrid],
    issues: Sequence[PaperIssue] = (),
) -> Dict[str, Any]:
    """``{"papers": [...], "issues": [...]}``, newest paper first."""
    library_root = Path(library_root)
    views = [_paper(library_root, paper, citations, grids) for paper in papers]
    views.sort(key=lambda view: view["sort"], reverse=True)
    known = {paper.id for paper in papers}
    return {
        "papers": views,
        "issues": [
            {"severity": issue.severity, "message": issue.message, "paper": _issue_paper(issue, known)}
            for issue in issues
        ],
    }


def _issue_paper(issue: PaperIssue, known: set) -> str:
    """Lint messages start with ``<paper id>:`` or ``<paper id> <material>:``."""
    head = issue.message.split(":", 1)[0].split(" ", 1)[0]
    return head if head in known else ""


def _paper(
    library_root: Path,
    paper: Paper,
    citations: Optional[Mapping[str, Citation]],
    grids: Mapping[str, ParsedGrid],
) -> Dict[str, Any]:
    citation = _citation(paper, citations)
    doi = _doi(paper, citation)
    year = citation.year if citation and citation.year else paper.year
    month = citation.month if citation else ""
    materials = [_material(library_root, paper, material, grids) for material in paper.materials]
    known = {material.id for material in paper.materials}
    loose = [_check(library_root, link, None) for link in paper.links if link.material not in known]
    return {
        "id": paper.id,
        "bibkey": paper.bibkey,
        "title": _title(paper, citation),
        "authors": citation.authors if citation else "",
        "year": year,
        "year_label": published_label(year, month),
        "sort": published_sort(year, month) or "",
        "journal": citation.journal if citation else "",
        "volume": citation.volume if citation else "",
        "pages": citation.pages if citation else "",
        "doi": doi,
        "pdf": paper.file,
        "has_citation": citation is not None,
        "nuclei": _nuclei(paper, grids),
        "potentials": _potentials(library_root, paper),
        "results": sorted({link.result for link in paper.links if link.result}),
        "materials": materials,
        "loose": loose,
        "notes": paper.notes,
    }


def _material(
    library_root: Path,
    paper: Paper,
    material: Material,
    grids: Mapping[str, ParsedGrid],
) -> Dict[str, Any]:
    grid = grids.get(material.parsed) if material.parsed else None
    latex_text = ""
    if material.latex:
        path = library_root / material.latex
        if path.is_file():
            latex_text = path.read_text(encoding="utf-8")
    image = material.image if Path(material.image).suffix.lower() in _IMAGE_SUFFIXES else ""
    file = material.file or (material.image if material.image and not image else "")
    links = [link for link in paper.links if link.material == material.id]
    view: Dict[str, Any] = {
        "id": material.id,
        "kind": material.kind,
        "title": material.title or material.id,
        "image": image,
        "file": file,
        "latex_path": material.latex,
        "latex": latex_text,
        "pdf_page": material.pdf_page,
        "parsed": material.parsed if grid is not None else "",
        "caption": grid.caption if grid else "",
        "notes": material.notes,
        "columns": [],
        "rows": [],
        "checks": [_check(library_root, link, grid) for link in links],
    }
    if grid is None:
        return view
    view["columns"] = [{"text": c.text, "latex": _strip_dollars(c.latex)} for c in grid.columns]
    targets: Dict[tuple, str] = {}
    for link in links:
        index = column_index(grid, link.column)
        if link.row is not None and index is not None:
            targets.setdefault((link.row, index), link.result)
    for row_index, cells in enumerate(grid.rows):
        row = []
        for index, cell in enumerate(cells):
            latex, plain = _cell_math(cell.text)
            out: Dict[str, Any] = {"text": plain}
            if latex:
                out["latex"] = latex
            if (row_index, index) in targets:
                out["result"] = targets[(row_index, index)]
            row.append(out)
        view["rows"].append(row)
    return view


def _check(library_root: Path, link, grid: Optional[ParsedGrid]) -> Dict[str, Any]:
    """One printed number next to the stored median, with a verdict.

    ``state`` is ``ok`` / ``mismatch`` for a direct link with a printed cell,
    ``derived`` when the paper adjusts the value, ``missing`` when the result
    is not in the library, ``nocell`` when row and column do not match the
    parsed table, and ``linked`` otherwise (a plot or an unparsed table).
    """
    cell = grid_cell(grid, link.row, link.column) if grid is not None else None
    printed = cell.text if cell else ""
    median = bundle_median(library_root, link.result)
    stored = ""
    if median is not None:
        stored = format_like_printed(median, printed) if printed else _short_number(median)
    if median is None:
        state = "missing"
    elif link.compare == "derived":
        state = "derived"
    elif grid is not None and link.row is not None and link.column and cell is None:
        state = "nocell"
    elif link.compare == "direct" and cell is not None:
        state = "mismatch" if direct_disagrees(cell.text, cell.value, median) else "ok"
    else:
        state = "linked"
    return {
        "label": link.label or link.result,
        "result": link.result,
        "compare": link.compare,
        "note": link.note,
        "row": link.row,
        "column": link.column,
        "printed": printed,
        "stored": stored,
        "state": state,
    }


def _short_number(value: float) -> str:
    return f"{value:.6g}"
