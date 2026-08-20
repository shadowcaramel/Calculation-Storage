"""
Table exports: LaTeX, TSV, CSV.

Generated from catalog values, never scraped from a rendered HTML table. That is
the whole point: selecting a table in a browser and pasting it produces stray
whitespace, merged cells, and hidden columns, whereas these strings are built
from the numbers themselves and are identical every time.

The asymmetric-uncertainty form ``$X^{+a}_{-b}$`` is assembled here too, since
writing it by hand is exactly where transcription errors appear.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Mapping, Optional, Sequence

#: Column key -> (LaTeX header, plain header)
COLUMN_HEADERS: dict[str, tuple[str, str]] = {
    "nucleus": ("Nucleus", "Nucleus"),
    "state": ("State", "State"),
    "observable": ("Observable", "Observable"),
    "value": ("Value", "Value"),
    "median": ("Median", "Median"),
    "err_low": ("$-\\sigma$", "err_low"),
    "err_high": ("$+\\sigma$", "err_high"),
    "N_models": ("$N_{\\mathrm{models}}$", "N_models"),
    "Nmax_final": ("$N_{\\max}^{u}$", "Nmax_final"),
    "units": ("Units", "Units"),
    "status": ("Status", "Status"),
    "id": ("Id", "Id"),
}

DEFAULT_COLUMNS: tuple[str, ...] = (
    "state",
    "observable",
    "value",
    "N_models",
    "Nmax_final",
)

#: Columns rendered in math mode in LaTeX output.
_MATH_COLUMNS = {"state", "value"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if value.is_integer():
            return str(int(value))
        return f"{value:.3f}"
    return str(value)


def _latex_escape(text: str) -> str:
    """Escape the characters that break a LaTeX table cell."""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def cell_value(row: Mapping[str, Any], column: str, for_latex: bool) -> str:
    """One cell, formatted for either LaTeX or plain text."""
    if column == "state":
        if for_latex:
            return _text(row.get("state_latex") or row.get("state_label"))
        return _text(row.get("state_label") or row.get("state_slug"))

    if column == "observable":
        if for_latex and row.get("observable_latex"):
            return _text(row.get("observable_latex"))
        return _text(row.get("observable_label") or row.get("observable"))

    if column == "value":
        if for_latex:
            latex = row.get("value_latex")
            return f"${latex}$" if latex else ""
        return _text(row.get("value_label"))

    return _text(row.get(column))


def _prepare_cell(row: Mapping[str, Any], column: str, for_latex: bool) -> str:
    text = cell_value(row, column, for_latex)
    if not for_latex:
        return text
    if column in _MATH_COLUMNS or (text.startswith("$") and text.endswith("$")):
        return text
    return _latex_escape(text)


def _alignment(columns: Sequence[str]) -> str:
    return "".join("l" if column in ("state", "observable", "id") else "c"
                   for column in columns)


def latex_table(
    rows: Iterable[Mapping[str, Any]],
    columns: Sequence[str] = DEFAULT_COLUMNS,
    caption: Optional[str] = None,
    label: Optional[str] = None,
) -> str:
    """A ``booktabs`` table ready to paste into a manuscript."""
    columns = list(columns)
    lines: list[str] = []

    if caption or label:
        lines.append("\\begin{table}[htbp]")
        lines.append("\\centering")

    lines.append(f"\\begin{{tabular}}{{{_alignment(columns)}}}")
    lines.append("\\toprule")
    lines.append(
        " & ".join(COLUMN_HEADERS.get(c, (c, c))[0] for c in columns) + " \\\\"
    )
    lines.append("\\midrule")

    for row in rows:
        lines.append(
            " & ".join(_prepare_cell(row, c, for_latex=True) for c in columns) + " \\\\"
        )

    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")

    if caption:
        lines.append(f"\\caption{{{caption}}}")
    if label:
        lines.append(f"\\label{{{label}}}")
    if caption or label:
        lines.append("\\end{table}")

    return "\n".join(lines)


def tsv_table(
    rows: Iterable[Mapping[str, Any]],
    columns: Sequence[str] = DEFAULT_COLUMNS,
) -> str:
    """Tab-separated text, which pastes cleanly into both LaTeX and Excel."""
    columns = list(columns)
    lines = ["\t".join(COLUMN_HEADERS.get(c, (c, c))[1] for c in columns)]
    for row in rows:
        lines.append(
            "\t".join(_prepare_cell(row, c, for_latex=False) for c in columns)
        )
    return "\n".join(lines)


def csv_table(
    rows: Iterable[Mapping[str, Any]],
    columns: Sequence[str] = DEFAULT_COLUMNS,
) -> str:
    """Comma-separated text for journal supplements and collaborators."""
    columns = list(columns)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([COLUMN_HEADERS.get(c, (c, c))[1] for c in columns])
    for row in rows:
        writer.writerow([_prepare_cell(row, c, for_latex=False) for c in columns])
    return buffer.getvalue().rstrip("\n")
