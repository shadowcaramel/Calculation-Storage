"""
Checks for a paper library. None of them stop the paper site from being written.

A DOI in ``papers.json`` that contradicts the bibliography is an error. Number
mismatches are warnings, and a ``derived`` link is not required to match.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

from paper_storage.bib import Citation, normalize_doi, normalize_text
from paper_storage.load import Paper, ParsedGrid, grid_cell
from paper_storage.numbers import bundle_median, direct_disagrees


@dataclass(frozen=True)
class PaperIssue:
    severity: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.message}"


def lint_papers(
    library_root: Path,
    papers: Iterable[Paper],
    *,
    bibliography: Optional[Mapping[str, Citation]] = None,
    grids: Optional[Mapping[str, ParsedGrid]] = None,
) -> List[PaperIssue]:
    """Cross-check citations, files, and linked numbers."""
    library_root = Path(library_root)
    grids = grids or {}
    issues: List[PaperIssue] = []
    seen: Dict[str, int] = {}
    for paper in papers:
        seen[paper.id] = seen.get(paper.id, 0) + 1
        issues.extend(_check_citation(paper, bibliography))
        issues.extend(_check_files(library_root, paper, grids))
        issues.extend(_check_links(library_root, paper, grids))
    for paper_id, count in seen.items():
        if count > 1:
            issues.append(
                PaperIssue("warning", f"{paper_id}: duplicated {count} times in papers.json")
            )
    return issues


def _check_citation(
    paper: Paper,
    bibliography: Optional[Mapping[str, Citation]],
) -> List[PaperIssue]:
    if bibliography is None:
        return []
    if not paper.bibkey:
        return [PaperIssue("warning", f"{paper.id}: no bibkey")]
    citation = bibliography.get(paper.bibkey)
    if citation is None:
        return [
            PaperIssue(
                "warning",
                f"{paper.id}: bibkey {paper.bibkey!r} is not in the bibliography",
            )
        ]
    issues: List[PaperIssue] = []
    if paper.doi and citation.doi:
        if normalize_doi(paper.doi) != normalize_doi(citation.doi):
            issues.append(
                PaperIssue(
                    "error",
                    f"{paper.id}: doi {paper.doi} does not match bibliography "
                    f"{normalize_doi(citation.doi)}",
                )
            )
    if paper.title and citation.title:
        if normalize_text(paper.title) != normalize_text(citation.title):
            issues.append(
                PaperIssue(
                    "warning",
                    f"{paper.id}: title does not match bibliography entry {paper.bibkey}",
                )
            )
    if paper.year and citation.year:
        if normalize_text(paper.year) != normalize_text(citation.year):
            issues.append(
                PaperIssue(
                    "warning",
                    f"{paper.id}: year {paper.year} does not match bibliography "
                    f"{citation.year}",
                )
            )
    return issues


def _check_files(
    library_root: Path,
    paper: Paper,
    grids: Mapping[str, ParsedGrid],
) -> List[PaperIssue]:
    issues: List[PaperIssue] = []
    if paper.file and not (library_root / paper.file).is_file():
        issues.append(PaperIssue("warning", f"{paper.id}: missing file {paper.file}"))
    for material in paper.materials:
        where = f"{paper.id} {material.id}"
        if material.image and not (library_root / material.image).is_file():
            issues.append(PaperIssue("warning", f"{where}: missing image {material.image}"))
        if material.latex and not (library_root / material.latex).is_file():
            issues.append(PaperIssue("warning", f"{where}: missing LaTeX {material.latex}"))
        if material.parsed_explicit and material.parsed not in grids:
            issues.append(
                PaperIssue("warning", f"{where}: missing parsed table {material.parsed}")
            )
    return issues


def _check_links(
    library_root: Path,
    paper: Paper,
    grids: Mapping[str, ParsedGrid],
) -> List[PaperIssue]:
    issues: List[PaperIssue] = []
    materials = {material.id: material for material in paper.materials}
    for link in paper.links:
        where = link.label or link.result
        if link.material and link.material not in materials:
            issues.append(
                PaperIssue(
                    "warning",
                    f"{paper.id}: link {where!r} names unknown material {link.material!r}",
                )
            )
        if link.compare not in ("", "direct", "derived"):
            issues.append(
                PaperIssue(
                    "warning",
                    f"{paper.id}: link {where!r} has compare {link.compare!r}; "
                    "expected direct or derived",
                )
            )
        if link.compare == "derived" and not link.note:
            issues.append(
                PaperIssue(
                    "warning",
                    f"{paper.id}: derived link {where!r} needs a note describing the adjustment",
                )
            )
        median = bundle_median(library_root, link.result)
        if median is None:
            issues.append(
                PaperIssue(
                    "warning",
                    f"{paper.id}: result {link.result} is not in the library",
                )
            )
            continue
        if link.compare != "direct":
            continue
        material = materials.get(link.material)
        grid = grids.get(material.parsed) if material and material.parsed else None
        if grid is None or link.row is None or not link.column:
            continue
        cell = grid_cell(grid, link.row, link.column)
        if cell is None:
            issues.append(
                PaperIssue(
                    "warning",
                    f"{paper.id}: link {where!r} does not match a cell "
                    f"(row {link.row}, column {link.column!r})",
                )
            )
            continue
        if direct_disagrees(cell.text, cell.value, median):
            issues.append(
                PaperIssue(
                    "warning",
                    f"{paper.id}: {where} prints {cell.text or cell.value}, "
                    f"stored median is {median}",
                )
            )
    return issues
