"""
Declared identity and its validation rules.

A state's identity is *declared* in config and treated as authoritative. These
rules only check that a declaration is internally consistent with physics
invariants; they never read source data, never inspect a prepared table, and
never try to infer identity from a sheet name. Preparing the tables is the
researcher's job and stays outside this system.

Stdlib only, so the early config check can run without pydantic installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from results_schema.nuclides import Nuclide, parse_nuclide
from results_schema.slugs import (
    observable_slug,
    parity_sign,
    state_slug,
    transition_slug,
)

# Keys recognised in an [identity.states."<sheet>"] table.
STATE_KEYS = (
    "nucleus",
    "J2",
    "parity",
    "T2",
    "index",
    "observable",
    "reference",
    "transition_to",
)


@dataclass(frozen=True)
class StateDeclaration:
    """One state as declared in config, after normalisation."""

    nucleus: str
    J2: int
    parity: str
    T2: int
    index: int = 1

    @property
    def nuclide(self) -> Nuclide:
        return parse_nuclide(self.nucleus)

    @property
    def slug(self) -> str:
        return state_slug(self.J2, self.parity, self.T2, self.index)

    def as_dict(self) -> dict[str, Any]:
        """State-only mapping, as stored inside ``result.json``."""
        return {
            "J2": self.J2,
            "parity": self.parity,
            "T2": self.T2,
            "index": self.index,
        }


def validate_state_declaration(
    nucleus: Any,
    J2: Any,
    parity: Any,
    T2: Any,
    index: Any,
    *,
    context: str = "",
) -> list[str]:
    """Check one declaration against physics invariants.

    Returns a list of human-readable problems; empty means the declaration is
    self-consistent. Collecting problems instead of raising lets the caller
    report every bad sheet in one pass rather than one per pipeline start.
    """
    where = f" ({context})" if context else ""
    problems: list[str] = []

    nuclide: Optional[Nuclide] = None
    try:
        nuclide = parse_nuclide(nucleus)
    except ValueError as exc:
        problems.append(f"{exc}{where}")

    def _as_int(value: Any, name: str) -> Optional[int]:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"{name} must be an integer, got {value!r}{where}")
            return None
        if isinstance(value, float) and not float(value).is_integer():
            problems.append(
                f"{name} must be an integer (quantum numbers are stored doubled, "
                f"so J=5/2 is J2=5), got {value!r}{where}"
            )
            return None
        return int(value)

    j2 = _as_int(J2, "J2")
    t2 = _as_int(T2, "T2")
    n = _as_int(index if index is not None else 1, "index")

    try:
        parity_sign(parity)
    except ValueError as exc:
        problems.append(f"{exc}{where}")

    if j2 is not None and j2 < 0:
        problems.append(f"J2 must be non-negative, got {j2}{where}")
    if t2 is not None and t2 < 0:
        problems.append(f"T2 must be non-negative, got {t2}{where}")
    if n is not None and n < 1:
        problems.append(
            f"index must be >= 1 (n counts states of the same J^pi, "
            f"starting at 1), got {n}{where}"
        )

    if nuclide is not None:
        a_parity = nuclide.A % 2
        if j2 is not None and j2 % 2 != a_parity:
            expected = "half-integer" if a_parity else "integer"
            problems.append(
                f"J2={j2} is inconsistent with A={nuclide.A}: spin must be "
                f"{expected} for A={nuclide.A}, so J2 must be "
                f"{'odd' if a_parity else 'even'}{where}"
            )
        if t2 is not None and t2 % 2 != a_parity:
            expected = "half-integer" if a_parity else "integer"
            problems.append(
                f"T2={t2} is inconsistent with A={nuclide.A}: isospin must be "
                f"{expected} for A={nuclide.A}, so T2 must be "
                f"{'odd' if a_parity else 'even'}{where}"
            )
        if t2 is not None and t2 < nuclide.Tz2:
            problems.append(
                f"T2={t2} is below 2|T_z|={nuclide.Tz2} for {nuclide.canonical} "
                f"(Z={nuclide.Z}, N={nuclide.N}); isospin cannot be smaller than "
                f"its projection{where}"
            )

    return problems


def build_state_declaration(
    entry: Mapping[str, Any],
    default_nucleus: Optional[str] = None,
    *,
    context: str = "",
) -> tuple[Optional[StateDeclaration], list[str]]:
    """Turn one ``[identity.states."<sheet>"]`` table into a declaration.

    Returns ``(declaration_or_None, problems)``. The declaration is ``None``
    whenever any problem was found, so callers never work with a half-valid
    identity.
    """
    where = f" ({context})" if context else ""
    problems: list[str] = []

    if not isinstance(entry, Mapping):
        return None, [f"Identity entry must be a table, got {entry!r}{where}"]

    unknown = sorted(set(entry) - set(STATE_KEYS))
    if unknown:
        problems.append(
            f"Unknown identity key(s) {unknown}{where}; expected any of "
            f"{list(STATE_KEYS)}"
        )

    nucleus = entry.get("nucleus", default_nucleus)
    if not nucleus:
        problems.append(
            f"No nucleus declared{where}: set [identity].nucleus for the run or "
            f"'nucleus' on this sheet"
        )

    for required in ("J2", "parity", "T2"):
        if required not in entry:
            problems.append(
                f"Missing required identity key '{required}'{where}. Isospin is "
                f"always declared explicitly; it is never derived from the nucleus."
            )

    if problems:
        return None, problems

    index = entry.get("index", 1)
    problems = validate_state_declaration(
        nucleus, entry["J2"], entry["parity"], entry["T2"], index, context=context
    )
    if problems:
        return None, problems

    return (
        StateDeclaration(
            nucleus=str(nucleus),
            J2=int(entry["J2"]),
            parity=parity_sign(entry["parity"]),
            T2=int(entry["T2"]),
            index=int(index),
        ),
        [],
    )


@dataclass(frozen=True)
class SheetIdentity:
    """Fully resolved identity for one data sheet.

    Produced once and consumed by both the early config check and the bundle
    writer, so validation and capture can never disagree about what a sheet is.
    """

    sheet: str
    nucleus: str
    state: StateDeclaration
    observable_name: str
    observable_path_slug: str
    transition_to: Optional[StateDeclaration] = None
    reference: Optional[Mapping[str, Any]] = None

    @property
    def kind(self) -> str:
        return "transition" if self.transition_to is not None else "state"

    @property
    def subject_slug(self) -> str:
        if self.transition_to is not None:
            return transition_slug(self.state.slug, self.transition_to.slug)
        return self.state.slug

    @property
    def family(self) -> str:
        return f"{self.nucleus}/{self.subject_slug}/{self.observable_path_slug}"


def resolve_sheet_identity(
    sheet: str,
    entry: Mapping[str, Any],
    default_nucleus: Optional[str],
    observable_name: str,
    observable_registry: Optional[Mapping[str, Any]] = None,
) -> tuple[Optional[SheetIdentity], list[str]]:
    """Resolve one sheet's declaration into a :class:`SheetIdentity`.

    Returns ``(identity_or_None, problems)``. Any problem yields ``None`` so a
    half-valid identity never reaches the bundle writer.
    """
    context = f"sheet '{sheet}'"
    state, problems = build_state_declaration(entry, default_nucleus, context=context)
    if state is None:
        return None, problems

    final_state: Optional[StateDeclaration] = None
    if entry.get("transition_to") is not None:
        final_state, final_problems = build_state_declaration(
            entry["transition_to"],
            state.nucleus,
            context=f"{context} transition_to",
        )
        problems.extend(final_problems)
        if final_state is not None and final_state.nucleus != state.nucleus:
            problems.append(
                f"Transition endpoints for {context} are in different nuclei "
                f"({state.nucleus} and {final_state.nucleus}). Declare a "
                f"cross-nucleus quantity with a 'reference' block instead."
            )
            final_state = None

    reference = entry.get("reference")
    if reference is not None:
        problems.extend(
            validate_reference_declaration(reference, state.nucleus, context=context)
        )

    name = entry.get("observable") or observable_name
    registry_entry: Mapping[str, Any] = {}
    if observable_registry:
        registry_entry = observable_registry.get(name) or {}

    try:
        path_slug = observable_slug(
            name,
            reference=reference if reference else None,
            subject_nucleus=state.nucleus,
            explicit_slug=registry_entry.get("slug"),
        )
    except ValueError as exc:
        problems.append(f"{exc} ({context})")
        path_slug = ""

    if problems:
        return None, problems

    return (
        SheetIdentity(
            sheet=sheet,
            nucleus=state.nucleus,
            state=state,
            observable_name=name,
            observable_path_slug=path_slug,
            transition_to=final_state,
            reference=reference,
        ),
        [],
    )


def validate_reference_declaration(
    reference: Mapping[str, Any],
    default_nucleus: Optional[str] = None,
    *,
    context: str = "",
) -> list[str]:
    """Validate a reference block, which needs an alias or a full state."""
    where = f" ({context})" if context else ""
    if not isinstance(reference, Mapping):
        return [f"Reference must be a table, got {reference!r}{where}"]

    problems: list[str] = []
    has_alias = bool(reference.get("alias"))
    state = reference.get("state")

    if not has_alias and not state:
        problems.append(
            f"Reference must declare 'alias' (e.g. 'gs') or a 'state' table{where}"
        )

    if state:
        nucleus = reference.get("nucleus", default_nucleus)
        problems.extend(
            validate_state_declaration(
                nucleus,
                state.get("J2"),
                state.get("parity"),
                state.get("T2"),
                state.get("index", 1),
                context=f"{context} reference" if context else "reference",
            )
        )

    convention = reference.get("convention")
    if convention is not None and not isinstance(convention, Mapping):
        problems.append(
            f"Reference 'convention' must be a table of key/value pairs, "
            f"got {convention!r}{where}"
        )

    return problems
