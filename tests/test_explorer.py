"""Tests for the explorer: the data file the build writes, and the app over it."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from results_library.annotations import lint_annotations, merge_annotation
from results_library.catalog import build_catalog
from results_library.cli import main as cli_main
from results_library.views.app import (
    DATA_FILENAME,
    EXPLORER_DIRNAME,
    EXPLORER_PAGE,
    build_explorer,
    headline_ids,
    matrix_columns,
)
from results_schema.models import Observable, Reference, ResultRecord, StateRecord, Subject, Variant

from tests.test_results_library import _c16_transition, _computed, _he6_record, _place


def _read_catalog(library: Path) -> dict:
    text = (library / EXPLORER_DIRNAME / DATA_FILENAME).read_text(encoding="utf-8")
    prefix, suffix = "window.CATALOG = ", ";\n"
    assert text.startswith(prefix) and text.endswith(suffix)
    return json.loads(text[len(prefix):-len(suffix)])


def _row(**fields) -> dict:
    base = {"lineage": "legacy", "family": "2H/1p-T0-n1/Eabs", "status": "probing"}
    base.update(fields)
    return base


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    root.mkdir()
    first = _he6_record("2026-08-18_15-02-11")
    second = _he6_record(
        "2026-08-19_10-00-00",
        computed=_computed(median=2.650, N_models=8),
        variant=Variant(
            selection_set="all_models",
            bounds={"Nmax": [2, 6], "hOmega": [13, 40]},
            potential="Daejeon16",
        ),
    )
    _place(root, first)
    _place(root, second)
    _place(root, _c16_transition("2026-08-20_09-00-00"), files={"histogram.png": b"\x89PNG"})
    root.joinpath("annotations.toml").write_text(
        f'["{first.id}"]\nstatus = "working"\nnote = "Own weights </script> here."\ntags = ["scan"]\n',
        encoding="utf-8",
    )
    return root


class TestHeadline:
    def test_status_beats_selection_order(self):
        rows = [
            _row(id="a", selection_set="19_convVP_loss_straight_ns", status="probing"),
            _row(id="b", selection_set="all_models", status="published"),
        ]
        assert headline_ids(rows) == {"b"}

    def test_legacy_selection_order(self):
        rows = [
            _row(id="ten", selection_set="10_loss_vp_straight_nsigma"),
            _row(id="all", selection_set="all_models"),
            _row(id="twenty-three", selection_set="23_loss_straight_ns"),
            _row(id="nineteen", selection_set="19_convVP_loss_straight_ns"),
        ]
        assert headline_ids(rows) == {"nineteen"}
        assert headline_ids([r for r in rows if r["id"] != "nineteen"]) == {"twenty-three"}
        assert headline_ids([r for r in rows if r["id"] in ("ten", "all")]) == {"ten"}

    def test_newest_run_breaks_ties(self):
        rows = [
            _row(id="old", selection_set="final", run_datetime="2023-06-01T10:00:00"),
            _row(id="new", selection_set="final", run_datetime="2023-06-09T10:00:00"),
        ]
        assert headline_ids(rows) == {"new"}

    def test_pin_wins(self):
        rows = [
            _row(id="best", selection_set="final", status="published"),
            _row(id="pinned", selection_set="all_models", headline=True),
        ]
        assert headline_ids(rows) == {"pinned"}

    def test_one_headline_per_lineage_and_family(self):
        rows = [
            _row(id="legacy-a"),
            _row(id="modern-a", lineage="modern"),
            _row(id="other", family="6Li/1p-T0-n1/Eabs"),
        ]
        assert headline_ids(rows) == {"legacy-a", "modern-a", "other"}

    def test_per_potential_heads_each_potential(self):
        rows = [
            _row(id="d16", potential="Daejeon16", status="published"),
            _row(id="jisp", potential="JISP16", run_datetime="2026-01-01"),
            _row(id="jisp-old", potential="JISP16", run_datetime="2025-01-01"),
        ]
        assert headline_ids(rows) == {"d16"}
        assert headline_ids(rows, per_potential=True) == {"d16", "jisp"}


class TestMatrixColumns:
    def test_columns_follow_the_groups_and_skip_missing_ones(self):
        rows = [
            _row(observable="rp", observable_latex="$r_p$", units="fm"),
            _row(observable="E"),
            _row(observable="Eabs", observable_latex="$E_{\\mathrm{abs}}$", units="MeV"),
            _row(observable="mu"),
            _row(observable="B(E2)"),
            _row(observable="Eexc", lineage="modern"),
        ]
        cols = matrix_columns(rows)
        assert [c["key"] for c in cols["legacy"]] == ["Eabs", "rp", "other"]
        assert [c["key"] for c in cols["modern"]] == ["Eexc"]
        eabs, rp, other = cols["legacy"]
        assert eabs["observables"] == ["Eabs", "E"] and eabs["group"] == "Energies"
        assert rp["latex"] == "r_p" and rp["units"] == "fm" and rp["group"] == "Radii"
        # Leftovers are ordered with the E2 observables first.
        assert other["observables"] == ["B(E2)", "mu"] and other["label"] == "Other observables"
        assert matrix_columns([_row(observable="B(E2)")])["legacy"][0]["label"] == "E2 and moments"


class TestHeadlineAnnotation:
    def test_merge_reads_true_only(self):
        assert merge_annotation({}, {"headline": True})["headline"] is True
        assert merge_annotation({}, {"headline": "yes"})["headline"] is False
        assert merge_annotation({}, {})["headline"] is False

    def test_lint_rejects_non_boolean(self):
        problems = lint_annotations({"x": {"headline": "yes"}}, {"x"})
        assert any("headline must be true or false" in p for p in problems)
        assert lint_annotations({"x": {"headline": True}}, {"x"}) == []


class TestDataFile:
    def test_build_writes_page_data_and_assets(self, library):
        frame, _ = build_catalog(library)
        page = build_explorer(library, frame)
        assert page == library / EXPLORER_PAGE
        html = page.read_text(encoding="utf-8")
        for asset in ("explorer/catalog.js", "explorer/explorer.js", "explorer/explorer.css", "explorer/katex/katex.min.js"):
            assert asset in html
            assert (library / asset).is_file()
        assert list((library / EXPLORER_DIRNAME / "fonts").glob("*.woff2"))
        assert (library / EXPLORER_DIRNAME / "katex" / "fonts").is_dir()

    def test_rows_carry_what_the_app_reads(self, library):
        frame, _ = build_catalog(library)
        build_explorer(library, frame)
        data = _read_catalog(library)
        assert data["headline_order"][:2] == ["final", "19_convVP_loss_straight_ns"]
        assert len(data["rows"]) == 3
        assert data["nuclei"]["6He"]["chart"] == {"Z": 2, "N": 4, "A": 6, "symbol": "He"}
        # Nmax and ħΩ are typeset like the classic site: N_{\max}, \hbar\Omega.
        assert data["axes"]["Nmax"]["latex"] == "N_{\\max}"
        assert data["axes"]["hOmega"]["latex"] == "\\hbar\\Omega"
        assert data["label_tex"][data["axes"]["Nmax"]["label"]] == "N_{\\max}"

        he6 = [r for r in data["rows"] if r["nucleus"] == "6He"]
        assert {r["selection_set"] for r in he6} == {"final", "all_models"}
        # Same run, family, potential and bounds: one trained ensemble.
        assert len({r["ensemble"] for r in he6}) == 1
        heads = [r for r in he6 if r["headline"]]
        assert len(heads) == 1 and heads[0]["status"] == "working"
        assert heads[0]["tags"] == ["scan"]
        assert heads[0]["nmax"] == [2, 6] and heads[0]["homega"] == [13, 40]
        assert heads[0]["latex"].startswith("\\begin{tabular}")
        assert heads[0]["observable"] == "Erel"
        assert heads[0]["level"] == {"J2": 0, "parity": "+", "T2": 2, "n": 2}
        assert sum(r["potential_headline"] for r in he6) == 1
        transition = next(r for r in data["rows"] if r["nucleus"] == "16C")
        assert transition["level"] is None
        assert [c["key"] for c in data["matrix"]["modern"]] == ["Erel", "other"]

    def test_bundle_paths_are_shortened_and_root_relative(self, library):
        frame, _ = build_catalog(library)
        build_explorer(library, frame)
        row = next(r for r in _read_catalog(library)["rows"] if r["nucleus"] == "6He")
        assert row["bundle"].startswith("bundles/")
        assert (library / row["bundle"]).is_dir()
        plot = row["plots"][0]
        assert plot["href"] == "@/histogram.png"
        assert (library / row["bundle"] / plot["href"][2:]).is_file()
        assert row["files"][0] == {"name": "bundle folder", "label": "", "href": row["bundle"]}

    def test_closing_tags_in_notes_are_escaped(self, library):
        frame, _ = build_catalog(library)
        build_explorer(library, frame)
        text = (library / EXPLORER_DIRNAME / DATA_FILENAME).read_text(encoding="utf-8")
        assert "</script>" not in text
        assert any("Own weights </script> here." == r["note"] for r in _read_catalog(library)["rows"])

    def test_paper_links_become_used_in(self, library):
        frame, _ = build_catalog(library)
        target = frame["id"].iloc[0]
        links = {target: [{"id": "mazur2024", "title": "Mazur 2024", "href": "paper-site/mazur2024.html"}]}
        build_explorer(library, frame, paper_links=links)
        data = _read_catalog(library)
        assert data["with_papers"] is True
        row = next(r for r in data["rows"] if r["id"] == target)
        assert row["papers"] == links[target]

    def test_paper_view_is_passed_through(self, library):
        frame, _ = build_catalog(library)
        papers = {"papers": [{"id": "p1", "title": "T", "materials": [], "loose": []}], "issues": []}
        build_explorer(library, frame, papers=papers)
        assert _read_catalog(library)["papers"] == papers
        build_explorer(library, frame)
        assert _read_catalog(library)["papers"] is None

    def test_rows_carry_the_learning_rate_schedule(self, library):
        frame, _ = build_catalog(library)
        frame = frame.assign(
            lr_schedule_label="cosine restarts, η₀ = 0.005",
            lr_schedule_detail="cosine restarts, η₀ = 0.005 (first_decay_steps = 40000)",
        )
        build_explorer(library, frame)
        row = _read_catalog(library)["rows"][0]
        assert row["lr_schedule_label"] == "cosine restarts, η₀ = 0.005"
        assert row["lr_schedule_detail"].endswith("(first_decay_steps = 40000)")

    def test_nmax_windows_are_integers(self, library):
        frame, _ = build_catalog(library)
        build_explorer(library, frame)
        for row in _read_catalog(library)["rows"]:
            assert all(v is None or isinstance(v, int) for v in row["nmax"])

    def test_cli_explorer_touches_only_the_explorer(self, library):
        pytest.importorskip("jinja2")
        assert cli_main(["catalog", "--library", str(library)]) == 0
        library.joinpath("papers.json").write_text('{"papers": []}', encoding="utf-8")
        assert cli_main(["explorer", "--with-papers", "--library", str(library)]) == 0
        assert (library / EXPLORER_PAGE).is_file()
        assert not (library / "index.html").exists()
        assert not (library / "paper-site").exists()
        assert _read_catalog(library)["papers"] == {"papers": [], "issues": []}

    def test_rebuild_replaces_the_folder(self, library):
        frame, _ = build_catalog(library)
        build_explorer(library, frame)
        stray = library / EXPLORER_DIRNAME / "stale.js"
        stray.write_text("old", encoding="utf-8")
        build_explorer(library, frame)
        assert not stray.exists()

    def test_cli_build_writes_explorer(self, library):
        pytest.importorskip("jinja2")
        pytest.importorskip("openpyxl")
        assert cli_main(["build", "--library", str(library), "--no-excel"]) == 0
        assert (library / EXPLORER_PAGE).is_file()
        assert (library / "index.html").is_file()


def _excitation(J2: int, parity: str, median: float, run_stamp: str) -> ResultRecord:
    return ResultRecord.build(
        subject=Subject.single("6He", StateRecord(J2=J2, parity=parity, T2=2, index=1)),
        observable=Observable(slug="Eexc", name="Eexc", latex="$E_{exc}$", units="MeV"),
        computed=_computed(median=median),
        run_stamp=run_stamp,
        observable_path_slug="Eexc_vs_gs",
        reference=Reference(nucleus="6He", alias="gs"),
        variant=Variant(selection_set="final", bounds={"Nmax": [2, 6], "hOmega": [13, 40]}, potential="Daejeon16"),
        artifacts={"histogram_plot": "histogram.png"},
        available=["histogram"],
    )


class TestInBrowser:
    """Open the built page in a headless browser and walk the main routes.

    Needs ``pip install playwright`` and ``playwright install chromium``, or
    ``EXPLORER_TEST_CHROMIUM`` pointing at a Chromium binary. Skipped otherwise.
    """

    def test_routes_render_without_errors(self, library):
        sync_api = pytest.importorskip("playwright.sync_api")
        frame, _ = build_catalog(library)
        page_path = build_explorer(library, frame)
        family = next(r for r in _read_catalog(library)["rows"] if r["nucleus"] == "6He")["family"]
        with sync_api.sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(executable_path=os.environ.get("EXPLORER_TEST_CHROMIUM") or None)
            except Exception as exc:  # no browser installed for this playwright
                pytest.skip(f"no Chromium for Playwright: {exc}")
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            base = page_path.as_uri()
            page.goto(base)
            assert page.locator("h1").inner_text().lower() == "modern library"
            assert page.locator(".brand svg.mark rect").count() == 10
            assert (page_path.parent / "explorer" / "logo.svg").is_file()
            assert page.locator("#main .panel-h h2").first.inner_text().lower() == "results at a glance"
            assert page.locator("table.matrix tbody tr").count() == 2
            assert page.locator("table.matrix a.mx").count() == 2
            assert page.locator("#main .panel-h h2").last.inner_text().lower() == "most recent runs"
            assert "6" in page.locator("#main .run .nuclide sup").all_inner_texts()
            page.goto(base + "#modern/n/6He")
            assert page.locator(".famrow").count() == 1
            page.goto(base + "#modern/f/" + family.replace("/", "%2F"))
            assert page.locator("table.pivot tbody tr").count() == 1
            assert page.locator('th:has(button[data-sort="date"])').get_attribute("aria-sort") == "descending"
            page.locator('button[data-sort="nmax"]').click()
            assert page.locator('th:has(button[data-sort="nmax"])').get_attribute("aria-sort") == "ascending"
            page.locator('button[data-sort="nmax"]').click()
            assert page.locator('th:has(button[data-sort="nmax"])').get_attribute("aria-sort") == "descending"
            page.locator("button.cell").first.click()
            # The panel opens on the hashchange that the click starts.
            page.locator("#insp").wait_for(state="visible")
            assert "result" in page.locator("#insp .eyebrow").first.inner_text().lower()
            page.goto(base + "#legacy")
            assert page.locator("h1").inner_text().lower() == "legacy library"
            assert page.locator("table.matrix").count() == 0
            page.goto(base + "#papers")
            assert page.locator("h1").inner_text().lower() == "papers"
            browser.close()
        assert errors == []

    def test_nucleus_with_a_spectrum_opens_on_its_level_scheme(self, tmp_path):
        sync_api = pytest.importorskip("playwright.sync_api")
        root = tmp_path / "spectrum"
        root.mkdir()
        _place(root, _excitation(4, "+", 1.80, "2026-09-01_10-00-00"))
        _place(root, _excitation(2, "-", 2.40, "2026-09-02_10-00-00"))
        frame, _ = build_catalog(root)
        page_path = build_explorer(root, frame)
        with sync_api.sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(executable_path=os.environ.get("EXPLORER_TEST_CHROMIUM") or None)
            except Exception as exc:  # no browser installed for this playwright
                pytest.skip(f"no Chromium for Playwright: {exc}")
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            base = page_path.as_uri()
            page.goto(base)
            # Two excited states in one cell draw as a small level scheme.
            assert page.locator("table.matrix svg.scheme").count() == 1
            page.goto(base + "#modern/n/6He")
            assert page.locator("svg.lscheme a.lvl").count() == 2
            # Lowest excitation energy first.
            assert page.locator("table.states tbody th").all_inner_texts() == ["2+", "1−"]
            page.locator('button[data-nview="list"]').click()
            assert page.locator(".famrow").count() == 2
            browser.close()
        assert errors == []

    def test_search_filters_and_keeps_its_view_in_the_link(self, library):
        sync_api = pytest.importorskip("playwright.sync_api")
        frame, _ = build_catalog(library)
        page_path = build_explorer(library, frame)
        with sync_api.sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(executable_path=os.environ.get("EXPLORER_TEST_CHROMIUM") or None)
            except Exception as exc:  # no browser installed for this playwright
                pytest.skip(f"no Chromium for Playwright: {exc}")
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            base = page_path.as_uri()
            page.goto(base + "#modern")
            # "/" opens the search with the box focused.
            page.keyboard.press("/")
            page.locator("#sq").wait_for()
            assert page.evaluate("document.activeElement.id") == "sq"
            assert page.locator("#sr-sum b").inner_text() == "2 families"
            page.keyboard.type("16C")
            assert page.locator("#sr-sum b").inner_text() == "1 family"
            assert "q=16C" in page.evaluate("location.hash")
            page.locator('button[data-sclear]').click()
            page.locator('[data-snuc="6He"]').click()
            assert page.locator("a.srow:not(.head)").count() == 1
            # The hash carries the view, so a link reopens it.
            page.goto(base + "#modern")
            page.goto(base + "#modern/search/col=other")
            assert page.locator("#sr-sum b").inner_text() == "1 family"
            assert "16" in page.locator("a.srow .nuclide sup").all_inner_texts()
            browser.close()
        assert errors == []
