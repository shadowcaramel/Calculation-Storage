"""
Human-readable labels derived from the structured identity.

Every human-facing surface (HTML page, Excel row, LaTeX table) renders these
labels rather than the slug, so readability is this module's responsibility and
the slug only has to be stable.

The state index ``n`` is omitted at ``n = 1`` and shown as ``(2)``, ``(3)``, ...
otherwise, which matches the ``(J^pi, T)(n)`` convention used in the field. The
rule is deliberately dataset-independent: ``(2+, T=1)`` always means ``n = 1``.

Stdlib only, so the early config check can run without pydantic installed.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from results_schema.nuclides import parse_nuclide
from results_schema.slugs import parity_sign, render_doubled_label

_PARITY_UNICODE = {"+": "\u207a", "-": "\u207b"}

# Axis / column display forms. These match the pipeline plot-label registry
# (``[postprocessing.prediction_plots.labels.*]``): matplotlib gets ``mathtext``,
# the HTML page gets Unicode, Copy LaTeX gets the math-mode string.
# A captured record may overlay these via ``column_labels``.
# Defaults match ``[postprocessing.prediction_plots.labels.*]`` in config.toml.
# HTML/Excel use Unicode (the site is opened as local files, with no MathJax).
# Copy LaTeX / .tex exports use the math-mode form.
_AXIS_UNICODE = {
    "hOmega": "\u0127\u03a9",  # ħΩ
    "Nmax": "N\u2098\u2090\u2093",  # Nₘₐₓ
    "Erel": "E\u1d63\u2091\u2097",  # Eᵣₑₗ
    "Eexc": "E\u2091\u2093c",  # Eₑₓc (no subscript c)
    "Eabs": "E_abs",
    "RMS": "R\u1d63\u2098\u209b",  # Rᵣₘₛ
    "rp": "r\u209a",  # rₚ
    "rpp": "r\u209a\u209a",  # rₚₚ
    "BSR": "BSR",
}
_AXIS_LATEX = {
    "hOmega": r"$\hbar\Omega$",
    "Nmax": r"$N_{\max}$",
    "Erel": r"$E_{\mathrm{rel}}$",
    "Eexc": r"$E_{\mathrm{exc}}$",
    "Eabs": r"$E_{\mathrm{abs}}$",
    "RMS": r"$R_{\mathrm{rms}}$",
    "rp": r"$r_p$",
    "rpp": r"$r_{\mathrm{pp}}$",
    "BSR": r"$\mathrm{BSR}$",
}


def _index_suffix(index: Any) -> str:
    """``(n)`` for n > 1, empty for n = 1."""
    n = int(index or 1)
    return "" if n == 1 else f"({n})"


# ---------------------------------------------------------------------------
# Single state
# ---------------------------------------------------------------------------

def state_unicode(state: Mapping[str, Any], show_isospin: bool = True) -> str:
    """``(2⁺, T=1)`` or ``(5/2⁻, T=5/2)(2)``."""
    spin = render_doubled_label(state["J2"])
    parity = _PARITY_UNICODE[parity_sign(state["parity"])]
    if show_isospin:
        isospin = render_doubled_label(state["T2"])
        core = f"({spin}{parity}, T={isospin})"
    else:
        core = f"({spin}{parity})"
    return f"{core}{_index_suffix(state.get('index', 1))}"


def state_latex(
    state: Mapping[str, Any],
    show_isospin: bool = True,
    wrap: bool = True,
) -> str:
    """``$(2^{+},\\ T{=}1)$`` or ``$(5/2^{-},\\ T{=}5/2)(2)$``."""
    spin = render_doubled_label(state["J2"])
    parity = parity_sign(state["parity"])
    if show_isospin:
        isospin = render_doubled_label(state["T2"])
        core = f"({spin}^{{{parity}}},\\ T{{=}}{isospin})"
    else:
        core = f"({spin}^{{{parity}}})"
    body = f"{core}{_index_suffix(state.get('index', 1))}"
    return f"${body}$" if wrap else body


# ---------------------------------------------------------------------------
# Subjects (single state or transition)
# ---------------------------------------------------------------------------

def _subject_states(subject: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if subject.get("kind") == "transition":
        return [subject["initial"]["state"], subject["final"]["state"]]
    return [subject["state"]]


def subject_unicode(subject: Mapping[str, Any], show_isospin: bool = True) -> str:
    """State label, or ``initial → final`` for a transition."""
    states = _subject_states(subject)
    parts = [state_unicode(s, show_isospin) for s in states]
    return " \u2192 ".join(parts)


def subject_latex(
    subject: Mapping[str, Any],
    show_isospin: bool = True,
    wrap: bool = True,
) -> str:
    """State label, or ``initial \\rightarrow final`` for a transition."""
    states = _subject_states(subject)
    parts = [state_latex(s, show_isospin, wrap=False) for s in states]
    body = " \\rightarrow ".join(parts)
    return f"${body}$" if wrap else body


# ---------------------------------------------------------------------------
# Nuclides
# ---------------------------------------------------------------------------

def nuclide_unicode(nucleus: str) -> str:
    """``¹⁶C``."""
    return parse_nuclide(nucleus).unicode_label


def nuclide_latex(nucleus: str, wrap: bool = True) -> str:
    """``$^{16}\\mathrm{C}$``."""
    body = parse_nuclide(nucleus).latex_label
    return f"${body}$" if wrap else body


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

def _convention_unicode(convention: Mapping[str, Any]) -> str:
    if not convention:
        return ""
    parts = []
    for key in sorted(convention):
        value = convention[key]
        if key == "evaluated_at_hOmega":
            parts.append(f"\u0127\u03a9={value}")
        else:
            parts.append(f"{key}={value}")
    return " at " + ", ".join(parts)


def reference_unicode(
    reference: Mapping[str, Any],
    subject_nucleus: Optional[str] = None,
    show_isospin: bool = True,
) -> str:
    """``¹⁶C (0⁺, T=2)`` or ``gs at ħΩ=16``, omitting a redundant nucleus."""
    parts: list[str] = []
    ref_nucleus = reference.get("nucleus")
    if ref_nucleus and (
        subject_nucleus is None or str(ref_nucleus) != str(subject_nucleus)
    ):
        parts.append(nuclide_unicode(str(ref_nucleus)))

    alias = reference.get("alias")
    state = reference.get("state")
    if state:
        parts.append(state_unicode(state, show_isospin))
    elif alias:
        parts.append(str(alias))

    text = " ".join(p for p in parts if p)
    return text + _convention_unicode(reference.get("convention") or {})


# ---------------------------------------------------------------------------
# Whole result
# ---------------------------------------------------------------------------

def result_unicode(
    nucleus: str,
    subject: Mapping[str, Any],
    observable_display: str,
    reference: Optional[Mapping[str, Any]] = None,
    show_isospin: bool = True,
) -> str:
    """One-line description, e.g. ``Erel(¹⁷C (5/2⁺, T=5/2) − ¹⁶C (0⁺, T=2))``."""
    subject_text = f"{nuclide_unicode(nucleus)} {subject_unicode(subject, show_isospin)}"
    if reference:
        ref_text = reference_unicode(reference, nucleus, show_isospin)
        return f"{observable_display}({subject_text} \u2212 {ref_text})"
    return f"{observable_display}({subject_text})"


def format_value_with_uncertainty(
    median: float,
    err_low: float,
    err_high: float,
    precision: int = 3,
) -> str:
    """``8.492^{+0.543}_{-0.749}`` in math mode, without delimiters.

    Written out here rather than at each call site so a paper table and the web
    page can never disagree about rounding.
    """
    return (
        f"{median:.{precision}f}^{{+{err_high:.{precision}f}}}"
        f"_{{-{err_low:.{precision}f}}}"
    )


# ---------------------------------------------------------------------------
# Input-column / axis labels (hOmega, Nmax, ...)
# ---------------------------------------------------------------------------

def column_label_from_plot_entry(
    name: str,
    entry: Optional[Mapping[str, Any]] = None,
) -> dict[str, str]:
    """Build the stored label block for one column from a plot-label table."""
    entry = entry or {}
    unicode = (
        entry.get("unicode")
        or _AXIS_UNICODE.get(name)
        or entry.get("display")
        or name
    )
    latex = entry.get("mathtext") or entry.get("latex") or _AXIS_LATEX.get(name)
    display = entry.get("display") or name
    unit = entry.get("unit") or entry.get("units") or ""
    out = {"display": str(display), "unicode": str(unicode)}
    if latex:
        out["latex"] = str(latex)
    if unit:
        out["unit"] = str(unit)
    return out


def axis_unicode(
    name: str,
    column_labels: Optional[Mapping[str, Any]] = None,
) -> str:
    """HTML/Excel form of an input column: ``hOmega -> ħΩ``."""
    if column_labels:
        entry = column_labels.get(name) or {}
        if isinstance(entry, Mapping) and entry.get("unicode"):
            return str(entry["unicode"])
    return _AXIS_UNICODE.get(name, name)


def observable_unicode(
    name: Optional[str],
    *,
    stored: Optional[str] = None,
    column_labels: Optional[Mapping[str, Any]] = None,
) -> str:
    """HTML/Excel form of an observable: ``Erel -> Eᵣₑₗ``."""
    if stored:
        return str(stored)
    if not name:
        return ""
    return axis_unicode(str(name), column_labels)


def collect_column_labels(
    plot_tables: Optional[Mapping[str, Any]] = None,
    extra_names: Optional[Iterable[str]] = None,
) -> dict[str, dict[str, str]]:
    """Merge a plot-label table with defaults for every named column."""
    tables = dict(plot_tables or {})
    names = {str(key) for key in tables}
    names.update(str(name) for name in (extra_names or []) if name)
    return {
        name: column_label_from_plot_entry(name, tables.get(name) or {})
        for name in sorted(names)
    }


def axis_latex(
    name: str,
    column_labels: Optional[Mapping[str, Any]] = None,
    wrap: bool = True,
) -> str:
    """Math-mode form of an input column: ``hOmega -> $\\hbar\\Omega$``."""
    if column_labels:
        entry = column_labels.get(name) or {}
        if isinstance(entry, Mapping) and entry.get("latex"):
            text = str(entry["latex"])
            if wrap and not (text.startswith("$") and text.endswith("$")):
                return f"${text}$"
            return text
    text = _AXIS_LATEX.get(name)
    if text:
        return text if wrap else text.strip("$")
    return name


def setup_label(
    bounds: Mapping[str, Any],
    column_labels: Optional[Mapping[str, Any]] = None,
) -> str:
    """``ħΩ [8, 50]; Nmax [4, 18]`` from a variant bounds table."""
    parts: list[str] = []
    for column, limits in bounds.items():
        if isinstance(limits, (list, tuple)) and len(limits) == 2:
            parts.append(
                f"{axis_unicode(str(column), column_labels)} [{limits[0]}, {limits[1]}]"
            )
    return "; ".join(parts)
