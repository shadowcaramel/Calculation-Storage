"""
``papers.json`` and the parsed number grids a skill writes beside a table.

The build displays this JSON. It does not read LaTeX tables itself.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping, Optional

logger = logging.getLogger(__name__)

PAPERS_FILENAME = "papers.json"


@dataclass
class PaperLink:
    """One printed number pointing at a stored calculation."""

    label: str
    result: str
    material: str = ""
    row: Optional[int] = None
    column: str = ""
    compare: str = ""
    note: str = ""


@dataclass
class Material:
    """A table or plot taken from the paper."""

    id: str
    kind: str
    title: str = ""
    latex: str = ""
    image: str = ""
    file: str = ""
    pdf_page: Optional[int] = None
    parsed: str = ""
    parsed_explicit: bool = False
    notes: List[str] = field(default_factory=list)


@dataclass
class Paper:
    """One article. Citation text comes from the bibliography, not from here."""

    id: str
    bibkey: str = ""
    file: str = ""
    title: str = ""
    doi: str = ""
    year: str = ""
    materials: List[Material] = field(default_factory=list)
    links: List[PaperLink] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ParsedColumn:
    id: str
    text: str
    latex: str = ""


@dataclass
class ParsedCell:
    text: str
    value: Optional[float] = None


@dataclass
class ParsedGrid:
    caption: str
    columns: List[ParsedColumn]
    rows: List[List[ParsedCell]]


@dataclass
class PapersLoad:
    """What ``papers.json`` yielded. ``ok`` is false when the file cannot be read."""

    papers: List[Paper]
    ok: bool = True
    message: str = ""


def papers_path(library_root: Path) -> Path:
    return Path(library_root) / PAPERS_FILENAME


def load_papers(library_root: Path) -> PapersLoad:
    """Read the manifest. A missing file is an empty, successful load."""
    path = papers_path(library_root)
    if not path.exists():
        return PapersLoad(papers=[])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return PapersLoad(papers=[], ok=False, message=str(exc))
    if not isinstance(data, Mapping):
        return PapersLoad(papers=[], ok=False, message="papers.json is not an object")

    raw_papers = data.get("papers") or []
    if not isinstance(raw_papers, list):
        return PapersLoad(papers=[], ok=False, message="papers.json has no 'papers' list")

    papers: List[Paper] = []
    for item in raw_papers:
        paper = _paper(item)
        if paper is not None:
            papers.append(paper)
    return PapersLoad(papers=papers)


def load_grid(library_root: Path, relative: str) -> Optional[ParsedGrid]:
    """Read a parsed table. Missing or malformed input is ``None``."""
    if not relative:
        return None
    path = Path(library_root) / relative
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None
    if not isinstance(data, Mapping):
        return None
    columns = [_column(item, index) for index, item in enumerate(data.get("columns") or [])]
    columns = [column for column in columns if column is not None]
    rows: List[List[ParsedCell]] = []
    for raw_row in data.get("rows") or []:
        if not isinstance(raw_row, Mapping):
            continue
        cells = [_cell(item) for item in (raw_row.get("cells") or [])]
        rows.append(cells)
    return ParsedGrid(
        caption=str(data.get("caption") or "").strip(),
        columns=columns,
        rows=rows,
    )


def default_parsed_path(latex_path: str) -> str:
    """``table1.tex`` is accompanied by ``table1.parsed.json`` when a skill wrote one."""
    if not latex_path:
        return ""
    path = Path(latex_path)
    return str(path.with_suffix(".parsed.json")).replace("\\", "/")


def column_index(grid: ParsedGrid, column: str) -> Optional[int]:
    """Match a link's column against the grid id or the header text."""
    wanted = str(column or "").strip()
    if not wanted:
        return None
    folded = wanted.casefold()
    for index, column_info in enumerate(grid.columns):
        if column_info.id == wanted or column_info.text == wanted:
            return index
    for index, column_info in enumerate(grid.columns):
        if column_info.id.casefold() == folded or column_info.text.casefold() == folded:
            return index
    return None


def grid_cell(grid: ParsedGrid, row: Optional[int], column: str) -> Optional[ParsedCell]:
    index = column_index(grid, column)
    if index is None or row is None or row < 0 or row >= len(grid.rows):
        return None
    cells = grid.rows[row]
    if index >= len(cells):
        return None
    return cells[index]


def _paper(item: Any) -> Optional[Paper]:
    if not isinstance(item, Mapping):
        return None
    paper_id = str(item.get("id") or "").strip()
    if not paper_id:
        return None
    materials = []
    for raw in item.get("materials") or []:
        material = _material(raw)
        if material is not None:
            materials.append(material)
    links = []
    for raw in item.get("links") or []:
        link = _link(raw)
        if link is not None:
            links.append(link)
    return Paper(
        id=paper_id,
        bibkey=str(item.get("bibkey") or "").strip(),
        file=str(item.get("file") or "").strip().replace("\\", "/"),
        title=str(item.get("title") or "").strip(),
        doi=str(item.get("doi") or "").strip(),
        year=str(item.get("year") or "").strip(),
        materials=materials,
        links=links,
        notes=_notes(item),
    )


def _material(item: Any) -> Optional[Material]:
    if not isinstance(item, Mapping):
        return None
    material_id = str(item.get("id") or "").strip()
    kind = str(item.get("kind") or "").strip().lower()
    if not material_id or kind not in ("table", "plot"):
        return None
    latex = str(item.get("latex") or "").strip().replace("\\", "/")
    parsed_raw = item.get("parsed")
    explicit = isinstance(parsed_raw, str) and bool(parsed_raw.strip())
    parsed = (
        str(parsed_raw).strip().replace("\\", "/")
        if explicit
        else default_parsed_path(latex)
    )
    page = item.get("pdf_page")
    pdf_page = int(page) if isinstance(page, int) and not isinstance(page, bool) else None
    return Material(
        id=material_id,
        kind=kind,
        title=str(item.get("title") or "").strip(),
        latex=latex,
        image=str(item.get("image") or "").strip().replace("\\", "/"),
        file=str(item.get("file") or "").strip().replace("\\", "/"),
        pdf_page=pdf_page,
        parsed=parsed,
        parsed_explicit=explicit,
        notes=_notes(item),
    )


def _notes(item: Mapping) -> List[str]:
    """Optional storage notes: ``note`` (one string) and ``notes`` (a list), in that order."""
    raw = [item.get("note")]
    extra = item.get("notes")
    raw.extend(extra if isinstance(extra, list) else [extra])
    return [text for text in (str(n).strip() for n in raw if isinstance(n, str)) if text]


def _link(item: Any) -> Optional[PaperLink]:
    if not isinstance(item, Mapping):
        return None
    result = str(item.get("result") or "").strip()
    if not result:
        return None
    row = item.get("row")
    row_index: Optional[int]
    if isinstance(row, int) and not isinstance(row, bool):
        row_index = row
    else:
        row_index = None
    compare = str(item.get("compare") or "").strip().lower()
    return PaperLink(
        label=str(item.get("label") or "").strip(),
        result=result,
        material=str(item.get("material") or "").strip(),
        row=row_index,
        column=str(item.get("column") or "").strip(),
        compare=compare,
        note=str(item.get("note") or "").strip(),
    )


def _column(item: Any, index: int) -> Optional[ParsedColumn]:
    if isinstance(item, str) and item.strip():
        text = item.strip()
        return ParsedColumn(id=text, text=text)
    if not isinstance(item, Mapping):
        return None
    text = str(item.get("text") or item.get("id") or "").strip()
    column_id = str(item.get("id") or text or f"column-{index}").strip()
    if not text and not column_id:
        return None
    return ParsedColumn(
        id=column_id,
        text=text or column_id,
        latex=str(item.get("latex") or "").strip(),
    )


def _cell(item: Any) -> ParsedCell:
    if isinstance(item, str):
        return ParsedCell(text=item)
    if isinstance(item, (int, float)) and not isinstance(item, bool):
        return ParsedCell(text=str(item), value=float(item))
    if not isinstance(item, Mapping):
        return ParsedCell(text="")
    value = item.get("value")
    number = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return ParsedCell(text=str(item.get("text") or "").strip(), value=number)
