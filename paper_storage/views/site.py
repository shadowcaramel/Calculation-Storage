"""
Static paper site under ``<library>/paper-site``.

Styles and KaTeX are copied from the calculation site's asset folder so the
two readers look alike. That copy is a filesystem read, not a Python import
of ``results_library``.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Mapping, Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from paper_storage.bib import Citation, normalize_doi, published_label, published_sort
from paper_storage.load import Material, Paper, ParsedGrid, column_index, grid_cell
from paper_storage.numbers import bundle_median, bundle_potential, format_like_printed

PAPER_SITE_DIRNAME = "paper-site"


def result_page_name(result_id: str) -> str:
    """Detail-page filename. The calculation site uses the same substitution."""
    return result_id.replace("/", "__") + ".html"


def render_site(
    library_root: Path,
    papers: List[Paper],
    citations: Optional[Mapping[str, Citation]],
    grids: Mapping[str, ParsedGrid],
) -> Path:
    """Write ``paper-site/index.html`` and one page per paper."""
    library_root = Path(library_root)
    site = library_root / PAPER_SITE_DIRNAME
    if site.exists():
        shutil.rmtree(site, ignore_errors=True)
    site.mkdir(parents=True, exist_ok=True)
    _copy_assets(site)

    calc_templates = (
        Path(__file__).resolve().parents[2] / "results_library" / "views" / "templates"
    )
    environment = Environment(
        loader=ChoiceLoader(
            [
                FileSystemLoader(str(Path(__file__).parent / "templates")),
                FileSystemLoader(str(calc_templates)),
            ]
        ),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    calculations_href = "../index.html" if (library_root / "index.html").is_file() else None
    cards = [_card(library_root, paper, citations, grids) for paper in papers]
    cards.sort(key=lambda card: card.get("year_sort") or "", reverse=True)

    index = environment.get_template("index.html")
    (site / "index.html").write_text(
        index.render(
            papers=cards,
            generated_at=generated_at,
            calculations_href=calculations_href,
            catalogue_page=True,
            root="",
        ),
        encoding="utf-8",
    )

    page = environment.get_template("paper.html")
    for paper in papers:
        (site / f"{paper.id}.html").write_text(
            page.render(
                paper=_paper_view(library_root, paper, citations, grids),
                generated_at=generated_at,
                calculations_href=calculations_href,
                root="",
            ),
            encoding="utf-8",
        )
    return site


def _card(
    library_root: Path,
    paper: Paper,
    citations: Optional[Mapping[str, Citation]],
    grids: Mapping[str, ParsedGrid],
) -> dict:
    citation = _citation(paper, citations)
    doi = _doi(paper, citation)
    year = citation.year if citation and citation.year else paper.year
    month = citation.month if citation else ""
    views = [
        _material_view(library_root, paper, material, grids)
        for material in paper.materials
    ]
    return {
        "id": paper.id,
        "href": f"{paper.id}.html",
        "title": _title(paper, citation),
        "authors": citation.authors if citation else "",
        "year": year,
        "year_label": published_label(year, month),
        "year_sort": published_sort(year, month),
        "journal": citation.journal if citation else "",
        "doi": doi,
        "doi_href": f"https://doi.org/{doi}" if doi else "",
        "nuclei": ", ".join(_nuclei(paper, grids)),
        "potentials": ", ".join(_potentials(library_root, paper)),
        "grids": [view for view in views if view["rows"]],
        "figures": [
            view for view in views
            if view["kind"] == "plot" and (view["image_href"] or view["file_href"])
        ],
    }


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_NUCLEUS = re.compile(r"(\d{1,3}[A-Z][a-z]?)")


def _nuclei(paper: Paper, grids: Mapping[str, ParsedGrid]) -> List[str]:
    """Linked nuclei first, then labels from a parsed Nucleus column."""
    found: List[str] = []
    for link in paper.links:
        nucleus = link.result.split("/", 1)[0].strip()
        if nucleus and nucleus not in found:
            found.append(nucleus)
    for material in paper.materials:
        grid = grids.get(material.parsed) if material.parsed else None
        if grid is None:
            continue
        index = next(
            (
                position
                for position, column in enumerate(grid.columns)
                if column.id.casefold() == "nucleus" or column.text.casefold() == "nucleus"
            ),
            None,
        )
        if index is None:
            continue
        for row in grid.rows:
            if index >= len(row):
                continue
            for label in _nucleus_labels(row[index].text):
                if label not in found:
                    found.append(label)
    return found


def _nucleus_labels(text: str) -> List[str]:
    cleaned = re.sub(r"\^\{(\d+)\}", r"\1", str(text or ""))
    cleaned = cleaned.replace("\\mathrm", "").replace("$", "")
    return _NUCLEUS.findall(cleaned)


def _potentials(library_root: Path, paper: Paper) -> List[str]:
    found: List[str] = []
    for link in paper.links:
        potential = bundle_potential(library_root, link.result)
        if potential and potential not in found:
            found.append(potential)
    return found


def _paper_view(
    library_root: Path,
    paper: Paper,
    citations: Optional[Mapping[str, Citation]],
    grids: Mapping[str, ParsedGrid],
) -> dict:
    citation = _citation(paper, citations)
    doi = _doi(paper, citation)
    pdf_href = _library_href(paper.file) if paper.file else ""
    return {
        "id": paper.id,
        "title": _title(paper, citation),
        "authors": citation.authors if citation else "",
        "year": citation.year if citation else paper.year,
        "journal": citation.journal if citation else "",
        "volume": citation.volume if citation else "",
        "pages": citation.pages if citation else "",
        "doi": doi,
        "doi_href": f"https://doi.org/{doi}" if doi else "",
        "pdf_href": pdf_href,
        "materials": [
            _material_view(library_root, paper, material, grids)
            for material in paper.materials
        ],
    }


def _material_view(
    library_root: Path,
    paper: Paper,
    material: Material,
    grids: Mapping[str, ParsedGrid],
) -> dict:
    grid = grids.get(material.parsed) if material.parsed else None
    latex_text = ""
    if material.latex:
        path = library_root / material.latex
        if path.is_file():
            latex_text = path.read_text(encoding="utf-8")
    suffix = Path(material.image).suffix.lower() if material.image else ""
    linked = _library_href(material.image) if material.image else ""
    is_image = suffix in _IMAGE_SUFFIXES
    image_href = linked if is_image else ""
    file_href = _library_href(material.file) if material.file else ""
    if not file_href and linked and not is_image:
        file_href = linked
    pdf_page_href = ""
    if material.pdf_page and paper_file_href(paper):
        pdf_page_href = f"{paper_file_href(paper)}#page={material.pdf_page}"
    columns = []
    rows = []
    if grid is not None:
        columns = [
            {"text": column.text, "latex": _strip_dollars(column.latex)}
            for column in grid.columns
        ]
        for row_index, cells in enumerate(grid.rows):
            rendered = []
            for column_index_value, cell in enumerate(cells):
                latex, plain = _cell_math(cell.text)
                rendered.append(
                    {
                        "text": cell.text,
                        "plain": plain,
                        "latex": latex,
                        "href": _cell_href(paper, material, row_index, column_index_value, grid),
                    }
                )
            rows.append(rendered)
    return {
        "id": material.id,
        "kind": material.kind,
        "title": material.title or material.id,
        "image_href": image_href,
        "file_href": file_href,
        "image_name": Path(material.image).name if material.image else "",
        "latex_text": latex_text,
        "latex_dom_id": f"latex-{paper.id}-{material.id}",
        "pdf_page_href": pdf_page_href,
        "caption": grid.caption if grid else "",
        "columns": columns,
        "rows": rows,
        "checks": _checks(library_root, paper, material, grid),
    }


def paper_file_href(paper: Paper) -> str:
    return _library_href(paper.file) if paper.file else ""


def _checks(library_root, paper: Paper, material: Material, grid: Optional[ParsedGrid]) -> List[dict]:
    checks = []
    for link in paper.links:
        if link.material != material.id:
            continue
        cell = grid_cell(grid, link.row, link.column) if grid is not None else None
        printed = cell.text if cell else ""
        median = bundle_median(library_root, link.result)
        checks.append(
            {
                "label": link.label or link.result,
                "compare": link.compare,
                "note": link.note,
                "printed": printed,
                "stored": (
                    format_like_printed(median, printed or str(median))
                    if median is not None
                    else ""
                ),
                "href": f"../site/results/{result_page_name(link.result)}",
            }
        )
    return checks


def _cell_href(
    paper: Paper,
    material: Material,
    row_index: int,
    column_index_value: int,
    grid: ParsedGrid,
) -> str:
    for link in paper.links:
        if link.material != material.id or link.row != row_index:
            continue
        matched = column_index(grid, link.column)
        if matched == column_index_value and link.result:
            return f"../site/results/{result_page_name(link.result)}"
    return ""


def _citation(
    paper: Paper, citations: Optional[Mapping[str, Citation]]
) -> Optional[Citation]:
    if not citations or not paper.bibkey:
        return None
    return citations.get(paper.bibkey)


def _title(paper: Paper, citation: Optional[Citation]) -> str:
    if citation and citation.title:
        return citation.title
    return paper.title or paper.id


def _doi(paper: Paper, citation: Optional[Citation]) -> str:
    raw = ""
    if citation and citation.doi:
        raw = citation.doi
    elif paper.doi:
        raw = paper.doi
    return normalize_doi(raw) if raw else ""


def _library_href(relative: str) -> str:
    """From ``paper-site/*.html`` up to a library-root relative path."""
    return "../" + relative.replace("\\", "/").lstrip("/")


def _strip_dollars(latex: str) -> str:
    text = str(latex or "").strip()
    while len(text) >= 2 and text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()
    return text


_MATH_MARK = re.compile(r"[\^_\\]")
_BRACE_SCRIPT = re.compile(r"(\^|_)\{([^{}]*)\}")
_SINGLE_SCRIPT = re.compile(r"(\^|_)([0-9A-Za-z+\-])")
_PROSE = re.compile(r"\s*(\([^()]*[A-Za-z][^()]*\))")
_SUPER = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", ".": "·",
}
_SUB = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", ".": "·",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
    "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
    "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
}


def _cell_math(text: str) -> tuple[str, str]:
    """KaTeX source and a Unicode fallback, or empty source when the cell is plain."""
    raw = str(text or "")
    if not raw or _MATH_MARK.search(raw) is None:
        return "", raw
    return _katex_source(raw), _unicode_math(raw)


def _katex_source(text: str) -> str:
    """Keep exponents as math and set prose in parentheses as text."""

    def repl(match: re.Match[str]) -> str:
        return r"\ \text{" + match.group(1) + "}"

    return _PROSE.sub(repl, text)


def _unicode_math(text: str) -> str:
    """Turn ``^{+0.007}`` and ``r_p`` into characters a page can show without KaTeX."""

    def script(match: re.Match[str]) -> str:
        table = _SUPER if match.group(1) == "^" else _SUB
        return "".join(table.get(character, character) for character in match.group(2))

    rendered = _BRACE_SCRIPT.sub(script, text)
    return _SINGLE_SCRIPT.sub(script, rendered)


def _copy_assets(site: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "results_library" / "views" / "assets"
    if not source.is_dir():
        return
    target = site / "assets"
    for asset in sorted(path for path in source.rglob("*") if path.is_file()):
        dest = target / asset.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(asset.read_bytes())
