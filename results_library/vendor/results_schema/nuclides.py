"""
Nuclide parsing for result identity.

Resolves a declared nucleus string such as ``"16C"`` into mass number, element
symbol, and proton/neutron counts, which the identity validation rules need in
order to check spin and isospin invariants.

Stdlib only, so the early config check can run without pydantic installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Element symbols indexed by Z - 1.
_SYMBOLS: tuple[str, ...] = (
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm",
    "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds",
    "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
)

Z_BY_SYMBOL: dict[str, int] = {sym: z for z, sym in enumerate(_SYMBOLS, start=1)}

# Case-insensitive lookup so "16c" and "6HE" are accepted and normalised.
_Z_BY_SYMBOL_CI: dict[str, int] = {sym.lower(): z for sym, z in Z_BY_SYMBOL.items()}

_NUCLIDE_RE = re.compile(r"^\s*(\d+)\s*([A-Za-z]{1,2})\s*$")
_SYMBOL_ONLY_RE = re.compile(r"^\s*([A-Za-z]{1,2})\s*$")

# Unicode superscript digits for display labels.
_SUPERSCRIPTS = str.maketrans("0123456789", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")


@dataclass(frozen=True)
class Nuclide:
    """A nuclide identified by mass number and element symbol."""

    A: int
    element: str
    Z: int

    @property
    def N(self) -> int:
        return self.A - self.Z

    @property
    def Tz2(self) -> int:
        """Twice the absolute isospin projection, i.e. ``|N - Z|``.

        Isospin obeys ``T >= |T_z|``, so this is the lower bound on ``T2``.
        """
        return abs(self.N - self.Z)

    @property
    def canonical(self) -> str:
        """Normalised ``{A}{Element}`` form, e.g. ``16C``."""
        return f"{self.A}{self.element}"

    @property
    def unicode_label(self) -> str:
        """Display form with a superscript mass number, e.g. ``¹⁶C``."""
        return f"{str(self.A).translate(_SUPERSCRIPTS)}{self.element}"

    @property
    def latex_label(self) -> str:
        """Math-mode form without delimiters, e.g. ``^{16}\\mathrm{C}``."""
        return f"^{{{self.A}}}\\mathrm{{{self.element}}}"

    def __str__(self) -> str:
        return self.canonical


def parse_nuclide(text: str) -> Nuclide:
    """Parse ``"16C"`` into a :class:`Nuclide`.

    Raises ``ValueError`` with a descriptive message on anything unparseable,
    an unknown element symbol, or a mass number smaller than the proton count.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            f"Nucleus must be a non-empty string like '16C', got {text!r}"
        )

    match = _NUCLIDE_RE.match(text)
    if match is None:
        raise ValueError(
            f"Cannot parse nucleus {text!r}. Expected mass number followed by "
            f"element symbol, e.g. '6He', '16C', '10Be'."
        )

    a_str, symbol = match.groups()
    z = _Z_BY_SYMBOL_CI.get(symbol.lower())
    if z is None:
        raise ValueError(
            f"Unknown element symbol {symbol!r} in nucleus {text!r}."
        )

    a = int(a_str)
    if a < z:
        raise ValueError(
            f"Nucleus {text!r} has mass number A={a} below proton number Z={z}, "
            f"which would give a negative neutron count."
        )

    # Normalise capitalisation from the lookup table.
    return Nuclide(A=a, element=_SYMBOLS[z - 1], Z=z)


def nucleus_sort_key(text: str) -> tuple[int, int, int, str]:
    """Periodic-table order: proton number Z, then mass number A.

    A bare element symbol (``He``) sorts before isotopes of that element
    (``4He``, ``6He``). Names that cannot be parsed sort last, alphabetically.
    """
    raw = str(text or "").strip()
    try:
        nuclide = parse_nuclide(raw)
        return (0, nuclide.Z, nuclide.A, nuclide.canonical)
    except ValueError:
        pass

    match = _SYMBOL_ONLY_RE.match(raw)
    if match:
        z = _Z_BY_SYMBOL_CI.get(match.group(1).lower())
        if z is not None:
            return (0, z, 0, _SYMBOLS[z - 1])

    return (1, 10**9, 10**9, raw)
