"""Tests for the paper-storage reader, kept independent of a calculation build."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from paper_storage.bib import normalize_doi, parse_bib  # noqa: E402
from paper_storage.build import build_papers  # noqa: E402
from paper_storage.lint import lint_papers  # noqa: E402
from paper_storage.load import load_grid, load_papers  # noqa: E402


BIB = """
% a comment that must not swallow the entry
@article{mazur2024machine,
  author = {Mazur, A. I. and Sharypov, R. E.},
  title = {Machine Learning in the Problem of Extrapolating {Variational} Calculations},
  year = 2024,
  doi = {10.3103/S0027134924700395},
  journal = {Mosc. Univ. Phys. Bull.},
  fjournal = {Moscow University Physics Bulletin},
}
"""

RESULT_ID = "6Li/1p-T0-n1/E/2024-06-01_12-00-00_aaaaaaaa/final_bbbbbbbb"


def _library(tmp_path: Path, name: str = "library") -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def _write_bundle(library: Path, median: float) -> None:
    parts = RESULT_ID.split("/")
    bundle = library.joinpath("bundles", "legacy", *parts)
    bundle.mkdir(parents=True)
    (bundle / "result.json").write_text(
        json.dumps({"id": RESULT_ID, "computed": {"median": median}}),
        encoding="utf-8",
    )


def _papers(library: Path, *, parsed: bool, compare: str = "direct", note: str = "", doi: str = "") -> None:
    table = library / "papers" / "example"
    table.mkdir(parents=True)
    (table / "table1.tex").write_text(
        r"\begin{tabular}{cc} $N$ & ours \\ 18 & $-32.034(4)$ \end{tabular}",
        encoding="utf-8",
    )
    (table / "table1.png").write_bytes(b"png")
    if parsed:
        (table / "table1.parsed.json").write_text(
            json.dumps(
                {
                    "caption": "Table 1",
                    "columns": [
                        {"id": "N", "text": "N"},
                        {"id": "Our calculations", "text": "ours"},
                    ],
                    "rows": [
                        {"cells": [{"text": "18"}, {"text": "-32.034(4)", "value": -32.034}]}
                    ],
                }
            ),
            encoding="utf-8",
        )
    paper = {
        "id": "example",
        "bibkey": "mazur2024machine",
        "file": "papers/example/article.pdf",
        "materials": [
            {
                "id": "table1",
                "kind": "table",
                "title": "Table 1",
                "latex": "papers/example/table1.tex",
                "image": "papers/example/table1.png",
            }
        ],
        "links": [
            {
                "label": "6Li, our calculation, Nmax = 18",
                "result": RESULT_ID,
                "material": "table1",
                "row": 0,
                "column": "Our calculations",
                "compare": compare,
            }
        ],
    }
    if doi:
        paper["doi"] = doi
    if note:
        paper["links"][0]["note"] = note
    (library / "papers.json").write_text(
        json.dumps({"papers": [paper]}),
        encoding="utf-8",
    )
    (table / "article.pdf").write_bytes(b"%PDF")


def test_missing_manifest_does_not_abort(tmp_path):
    library = _library(tmp_path)
    result = build_papers(library)
    assert result.ok
    text = (result.site / "index.html").read_text(encoding="utf-8")
    assert "No papers" in text


def test_bib_doi_mismatch_is_reported(tmp_path):
    library = _library(tmp_path)
    _write_bundle(library, -32.034)
    _papers(library, parsed=True, doi="10.9999/wrong")
    bib = library / "mini.bib"
    bib.write_text(BIB, encoding="utf-8")
    result = build_papers(library, bibliography=bib)
    assert result.ok
    joined = "\n".join(str(issue) for issue in result.issues)
    assert "[error]" in joined
    assert "10.9999/wrong" in joined
    index = (result.site / "index.html").read_text(encoding="utf-8")
    assert "Moscow University Physics Bulletin" in index


def test_parsed_grid_is_shown_beside_the_screenshot(tmp_path):
    library = _library(tmp_path)
    _write_bundle(library, -32.034)
    _papers(library, parsed=True)
    result = build_papers(library)
    page = (result.site / "example.html").read_text(encoding="utf-8")
    assert 'class="results parsed-grid"' in page
    assert "-32.034(4)" in page
    assert "table1.png" in page
    assert 'class="latex-spoiler"' in page
    assert f"../site/results/{RESULT_ID.replace('/', '__')}.html" in page


def test_missing_parsed_grid_does_not_invent_cells(tmp_path):
    library = _library(tmp_path)
    _papers(library, parsed=False)
    result = build_papers(library)
    page = (result.site / "example.html").read_text(encoding="utf-8")
    assert "parsed-grid" not in page
    assert "table1.png" in page
    assert r"\begin{tabular}" in page


def test_direct_mismatch_warns_and_derived_mismatch_does_not(tmp_path):
    library = _library(tmp_path)
    _write_bundle(library, -32.040)
    _papers(library, parsed=True, compare="direct")
    loaded = load_papers(library)
    grids = {
        "papers/example/table1.parsed.json": load_grid(
            library, "papers/example/table1.parsed.json"
        )
    }
    direct = lint_papers(library, loaded.papers, grids=grids)
    assert any("stored median" in issue.message for issue in direct)

    derived_library = _library(tmp_path, "derived")
    _write_bundle(derived_library, -30.0)
    _papers(
        derived_library,
        parsed=True,
        compare="derived",
        note="threshold energy subtracted",
    )
    loaded = load_papers(derived_library)
    grids = {
        "papers/example/table1.parsed.json": load_grid(
            derived_library, "papers/example/table1.parsed.json"
        )
    }
    derived = lint_papers(derived_library, loaded.papers, grids=grids)
    assert not any("stored median" in issue.message for issue in derived)

    bare = _library(tmp_path, "bare")
    _write_bundle(bare, -30.0)
    _papers(bare, parsed=True, compare="derived", note="")
    loaded = load_papers(bare)
    grids = {
        "papers/example/table1.parsed.json": load_grid(
            bare, "papers/example/table1.parsed.json"
        )
    }
    missing_note = lint_papers(bare, loaded.papers, grids=grids)
    assert any("needs a note" in issue.message for issue in missing_note)


def test_catalogue_lists_nuclei_potentials_and_a_grid(tmp_path):
    library = _library(tmp_path, "catalogue")
    _write_bundle(library, -32.034)
    bundle = library.joinpath("bundles", "legacy", *RESULT_ID.split("/"), "result.json")
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["variant"] = {"potential": "Daejeon16"}
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    _papers(library, parsed=True)
    parsed = json.loads((library / "papers" / "example" / "table1.parsed.json").read_text(encoding="utf-8"))
    parsed["columns"].insert(0, {"id": "Nucleus", "text": "Nucleus"})
    for row in parsed["rows"]:
        row["cells"].insert(0, {"text": "6He (g.s.)"})
    (library / "papers" / "example" / "table1.parsed.json").write_text(
        json.dumps(parsed), encoding="utf-8"
    )
    result = build_papers(library)
    page = (result.site / "index.html").read_text(encoding="utf-8")
    assert "6Li" in page
    assert "6He" in page
    assert "Daejeon16" in page
    assert "hide-grid" in page
    assert 'class="mode-switch storage-toggle"' in page
    assert "Modern" not in page
    assert "paper-block" in page
    assert "<th" not in page.split("paper-block", 1)[0]


def test_asymmetric_uncertainty_is_typeset(tmp_path):
    library = _library(tmp_path, "math")
    _papers(library, parsed=True)
    parsed = {
        "columns": [{"id": "value", "text": "Value"}],
        "rows": [{"cells": [{"text": "-29.429^{+0.007}_{-0.005}", "value": -29.429}]}],
    }
    (library / "papers" / "example" / "table1.parsed.json").write_text(
        json.dumps(parsed), encoding="utf-8"
    )
    result = build_papers(library)
    page = (result.site / "example.html").read_text(encoding="utf-8")
    assert "data-tex" in page
    assert "^{+0.007}" in page
    assert "⁺" in page
    assert "₀" in page


def test_bibliography_braces_and_doi_prefix():
    entries = parse_bib(BIB)
    citation = entries["mazur2024machine"]
    assert "Variational" in citation.title
    assert citation.journal == "Moscow University Physics Bulletin"
    assert normalize_doi(citation.doi) == "10.3103/s0027134924700395"
    assert normalize_doi("https://doi.org/10.3103/S0027134924700395") == normalize_doi(
        citation.doi
    )


def test_real_publications_file_when_present():
    path = Path(r"G:\My Drive\!ML\2026 rework\bibliography\my_publications.bib")
    if not path.is_file():
        pytest.skip("my_publications.bib is not on this machine")
    entries = parse_bib(path.read_text(encoding="utf-8"))
    citation = entries["mazur2024machine"]
    assert normalize_doi(citation.doi) == "10.3103/s0027134924700395"
    assert "2024" in citation.year
    assert "Machine Learning" in citation.title
