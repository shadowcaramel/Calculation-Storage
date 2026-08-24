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

import re
from typing import Any, Iterable, Mapping, Optional

from results_schema.nuclides import parse_nuclide
from results_schema.slugs import parity_sign, render_doubled_label

_PARITY_UNICODE = {"+": "\u207a", "-": "\u207b"}

# Axis / column display forms. Matplotlib gets ``mathtext`` from
# ``[postprocessing.prediction_plots.labels.*]``; HTML and Excel get Unicode
# derived from that string. Copy LaTeX keeps the math-mode form.
# A captured record may overlay these via ``column_labels``.
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

# Unicode sub/superscripts that exist as dedicated characters. A script that
# contains any other letter falls back to ``_text`` / ``^text``.
_SUBSCRIPT = {
    "0": "\u2080", "1": "\u2081", "2": "\u2082", "3": "\u2083", "4": "\u2084",
    "5": "\u2085", "6": "\u2086", "7": "\u2087", "8": "\u2088", "9": "\u2089",
    "+": "\u208a", "-": "\u208b", "=": "\u208c", "(": "\u208d", ")": "\u208e",
    "a": "\u2090", "e": "\u2091", "h": "\u2095", "i": "\u1d62", "j": "\u2c7c",
    "k": "\u2096", "l": "\u2097", "m": "\u2098", "n": "\u2099", "o": "\u2092",
    "p": "\u209a", "r": "\u1d63", "s": "\u209b", "t": "\u209c", "u": "\u1d64",
    "v": "\u1d65", "x": "\u2093",
}
_SUPERSCRIPT = {
    "0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3", "4": "\u2074",
    "5": "\u2075", "6": "\u2076", "7": "\u2077", "8": "\u2078", "9": "\u2079",
    "+": "\u207a", "-": "\u207b", "=": "\u207c", "(": "\u207d", ")": "\u207e",
    "n": "\u207f", "i": "\u2071",
}

# Longest-first so ``\Omega`` wins over a hypothetical ``\O``.
_MATHTEXT_MACROS = {
    "varepsilon": "\u03b5", "vartheta": "\u03d1", "varrho": "\u03f1",
    "varsigma": "\u03c2", "varphi": "\u03c6", "hbar": "\u0127",
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "delta": "\u03b4",
    "epsilon": "\u03b5", "zeta": "\u03b6", "eta": "\u03b7", "theta": "\u03b8",
    "iota": "\u03b9", "kappa": "\u03ba", "lambda": "\u03bb", "mu": "\u03bc",
    "nu": "\u03bd", "xi": "\u03be", "pi": "\u03c0", "rho": "\u03c1",
    "sigma": "\u03c3", "tau": "\u03c4", "upsilon": "\u03c5", "phi": "\u03c6",
    "chi": "\u03c7", "psi": "\u03c8", "omega": "\u03c9",
    "Gamma": "\u0393", "Delta": "\u0394", "Theta": "\u0398", "Lambda": "\u039b",
    "Xi": "\u039e", "Pi": "\u03a0", "Sigma": "\u03a3", "Phi": "\u03a6",
    "Psi": "\u03a8", "Omega": "\u03a9",
    "infty": "\u221e", "pm": "\u00b1", "times": "\u00d7", "cdot": "\u00b7",
    "circ": "\u2218", "ell": "\u2113",
    "max": "max", "min": "min",
}
_MACRO_NAMES = tuple(sorted(_MATHTEXT_MACROS, key=len, reverse=True))
_MACRO_PATTERN = re.compile(
    r"\\(" + "|".join(re.escape(name) for name in _MACRO_NAMES) + r")\b"
)
_ROMAN_PATTERN = re.compile(r"\\(?:mathrm|text|operatorname)\{([^{}]*)\}")
_SPACING_PATTERN = re.compile(r"\\[,;:! ]|~")
_BRACED_SUB = re.compile(r"_\{([^{}]*)\}")
_BRACED_SUP = re.compile(r"\^\{([^{}]*)\}")
_SINGLE_SUB = re.compile(r"_([A-Za-z0-9+\-])")
_SINGLE_SUP = re.compile(r"\^([A-Za-z0-9+\-])")
_UNKNOWN_MACRO = re.compile(r"\\([A-Za-z]+)")
_LEFTOVER_BRACES = re.compile(r"[{}]")


def _script_or_fallback(text: str, mapping: Mapping[str, str], prefix: str) -> str:
    converted: list[str] = []
    for char in text:
        if char == " ":
            continue
        mapped = mapping.get(char)
        if mapped is None:
            return f"{prefix}{text}"
        converted.append(mapped)
    return "".join(converted)


def mathtext_to_unicode(text: Optional[str]) -> str:
    """Turn matplotlib mathtext into a Unicode label for HTML and Excel.

    Covers the subset used in the plot-label table (``\\hbar``, ``_{...}``,
    ``\\mathrm{...}``, Greek letters). Config only needs to store mathtext;
    Unicode is derived. A leftover ``unicode =`` in a label table still wins.
    """
    if not text:
        return ""
    body = str(text).strip()
    if body.startswith("$") and body.endswith("$") and len(body) >= 2:
        body = body[1:-1]
    body = _SPACING_PATTERN.sub("", body)
    for _ in range(8):
        updated = _ROMAN_PATTERN.sub(r"\1", body)
        if updated == body:
            break
        body = updated
    body = _MACRO_PATTERN.sub(lambda match: _MATHTEXT_MACROS[match.group(1)], body)
    body = _SINGLE_SUB.sub(
        lambda match: _script_or_fallback(match.group(1), _SUBSCRIPT, "_"), body
    )
    body = _SINGLE_SUP.sub(
        lambda match: _script_or_fallback(match.group(1), _SUPERSCRIPT, "^"), body
    )
    body = _BRACED_SUB.sub(
        lambda match: _script_or_fallback(match.group(1), _SUBSCRIPT, "_"), body
    )
    body = _BRACED_SUP.sub(
        lambda match: _script_or_fallback(match.group(1), _SUPERSCRIPT, "^"), body
    )
    body = _UNKNOWN_MACRO.sub(r"\1", body)
    body = _LEFTOVER_BRACES.sub("", body)
    return re.sub(r"\s+", " ", body).strip()


_AXIS_UNICODE = {
    name: mathtext_to_unicode(latex) for name, latex in _AXIS_LATEX.items()
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
    latex = entry.get("mathtext") or entry.get("latex") or _AXIS_LATEX.get(name)
    unicode = (
        entry.get("unicode")
        or mathtext_to_unicode(latex)
        or _AXIS_UNICODE.get(name)
        or entry.get("display")
        or name
    )
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
    potential: Optional[str] = None,
) -> str:
    """``Daejeon16; ħΩ [8, 50]; Nmax [4, 18]`` from a variant bounds table."""
    parts: list[str] = []
    if potential:
        parts.append(str(potential))
    for column, limits in bounds.items():
        if isinstance(limits, (list, tuple)) and len(limits) == 2:
            parts.append(
                f"{axis_unicode(str(column), column_labels)} [{limits[0]}, {limits[1]}]"
            )
    return "; ".join(parts)
