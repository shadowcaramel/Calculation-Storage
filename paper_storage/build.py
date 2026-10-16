"""
Build the paper site from ``papers.json``.

Does not import ``results_library``. The calculation command calls
:func:`build_papers` only when ``--with-papers`` is set, then passes the
returned link map into the calculation site.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from paper_storage.bib import Citation, load_bibliography
from paper_storage.lint import PaperIssue, lint_papers
from paper_storage.load import PAPERS_FILENAME, Paper, ParsedGrid, PapersLoad, load_grid, load_papers
from paper_storage.views.explorer import explorer_papers
from paper_storage.views.site import PAPER_SITE_DIRNAME, render_site

logger = logging.getLogger(__name__)


@dataclass
class PaperBuild:
    ok: bool
    site: Path
    links: Dict[str, List[dict]] = field(default_factory=dict)
    issues: List[PaperIssue] = field(default_factory=list)
    #: What the explorer's Papers view reads; see :func:`explorer_papers`.
    explorer: Optional[dict] = None


@dataclass
class _Prepared:
    papers: List[Paper]
    citations: Optional[Dict[str, Citation]]
    grids: Dict[str, ParsedGrid]
    issues: List[PaperIssue]
    links: Dict[str, List[dict]]


def _prepare(library_root: Path, loaded: PapersLoad, bibliography: Optional[Path]) -> _Prepared:
    citations = _citations(bibliography)
    grids = _grids(library_root, loaded)
    issues = lint_papers(library_root, loaded.papers, bibliography=citations, grids=grids)
    return _Prepared(
        papers=loaded.papers,
        citations=citations,
        grids=grids,
        issues=issues,
        links=result_links(loaded.papers, citations),
    )


def build_papers(
    library_root: Path,
    bibliography: Optional[Path] = None,
) -> PaperBuild:
    """Write ``paper-site/`` and return the result-id-to-papers map.

    A missing ``papers.json`` still writes an empty site (``ok`` stays true).
    Unreadable JSON sets ``ok`` false after writing nothing.
    """
    library_root = Path(library_root)
    loaded = load_papers(library_root)
    site = library_root / PAPER_SITE_DIRNAME
    if not loaded.ok:
        return PaperBuild(
            ok=False,
            site=site,
            issues=[PaperIssue("error", loaded.message or "Could not read papers.json")],
        )

    prepared = _prepare(library_root, loaded, bibliography)
    render_site(library_root, prepared.papers, prepared.citations, prepared.grids)
    _write_links(library_root, prepared.links)
    _copy_manifest(library_root)
    return PaperBuild(
        ok=True,
        site=site,
        links=prepared.links,
        issues=prepared.issues,
        explorer=_explorer(library_root, prepared),
    )


def read_papers(
    library_root: Path,
    bibliography: Optional[Path] = None,
) -> PaperBuild:
    """Everything :func:`build_papers` returns, without writing ``paper-site/``.

    For refreshing only the explorer: the links and the Papers view come from
    the same inputs, but nothing in the library is touched.
    """
    library_root = Path(library_root)
    loaded = load_papers(library_root)
    site = library_root / PAPER_SITE_DIRNAME
    if not loaded.ok:
        return PaperBuild(
            ok=False,
            site=site,
            issues=[PaperIssue("error", loaded.message or "Could not read papers.json")],
        )
    prepared = _prepare(library_root, loaded, bibliography)
    return PaperBuild(
        ok=True,
        site=site,
        links=prepared.links,
        issues=prepared.issues,
        explorer=_explorer(library_root, prepared),
    )


def _explorer(library_root: Path, prepared: _Prepared) -> dict:
    return explorer_papers(
        library_root, prepared.papers, prepared.citations, prepared.grids, prepared.issues
    )


def result_links(
    papers: List[Paper],
    citations: Optional[Dict[str, Citation]],
) -> Dict[str, List[dict]]:
    """Map each calculation id to the papers that name it.

    ``href`` is relative to the library root. The calculation site turns that
    into a page-relative link and does not import this package to do so.
    """
    mapping: Dict[str, List[dict]] = {}
    for paper in papers:
        title = _display_title(paper, citations)
        entry = {
            "id": paper.id,
            "title": title,
            "href": f"{PAPER_SITE_DIRNAME}/{paper.id}.html",
        }
        seen = set()
        for link in paper.links:
            if not link.result or link.result in seen:
                continue
            seen.add(link.result)
            mapping.setdefault(link.result, []).append(dict(entry))
    return mapping


def _display_title(paper: Paper, citations: Optional[Dict[str, Citation]]) -> str:
    if citations and paper.bibkey and paper.bibkey in citations:
        title = citations[paper.bibkey].title
        if title:
            return title
    return paper.title or paper.id


def _citations(bibliography: Optional[Path]) -> Optional[Dict[str, Citation]]:
    if bibliography is None:
        return None
    try:
        return load_bibliography(bibliography)
    except OSError as exc:
        logger.warning("Could not read bibliography %s: %s", bibliography, exc)
        return None


def _grids(library_root: Path, loaded: PapersLoad) -> Dict[str, ParsedGrid]:
    grids: Dict[str, ParsedGrid] = {}
    for paper in loaded.papers:
        for material in paper.materials:
            if not material.parsed or material.parsed in grids:
                continue
            grid = load_grid(library_root, material.parsed)
            if grid is not None:
                grids[material.parsed] = grid
    return grids


def _write_links(library_root: Path, links: Dict[str, List[dict]]) -> None:
    path = library_root / PAPER_SITE_DIRNAME / "links.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"results": links}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _copy_manifest(library_root: Path) -> None:
    source = library_root / PAPERS_FILENAME
    if not source.is_file():
        return
    target = library_root / PAPER_SITE_DIRNAME / PAPERS_FILENAME
    target.write_bytes(source.read_bytes())
