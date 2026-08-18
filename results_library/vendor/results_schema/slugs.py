"""
Slug construction and parsing for result identity.

A slug is the filesystem- and URL-safe encoding of a state, an observable, or a
whole result id. Slugs are always *derived* from the structured declaration,
never parsed out of source data, so changing the slug format is a regeneration
rather than a data migration.

State slug form mirrors the ``(J^pi, T)(n)`` notation order::

    {spin}{parity}-T{isospin}-n{index}

    2p-T1-n1        (2+,  T=1)
    5_2p-T5_2-n1    (5/2+, T=5/2)
    0p-T1-n2        (0+,  T=1)(2)
    1m-T1-n1        (1-,  T=1)

Spin and isospin are stored doubled so they stay integers; ``_2`` in a slug
always means "halves" and never an index. The index always follows ``-n`` and is
always present, because whether a second state with the same quantum numbers
exists is a property of the dataset, not of the state -- omitting it would let a
later calculation retroactively change an existing id.

Stdlib only, so the early config check can run without pydantic installed.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

TRANSITION_SEP = "--to--"

STATE_SLUG_RE = re.compile(r"^(\d+(?:_2)?)([pm])-T(\d+(?:_2)?)-n(\d+)$")
_DOUBLED_TOKEN_RE = re.compile(r"^(\d+)(_2)?$")
_SAFE_SLUG_RE = re.compile(r"^[A-Za-z0-9_]+$")

_PARITY_TO_LETTER = {"+": "p", "-": "m", 1: "p", -1: "m", "p": "p", "m": "m"}
_LETTER_TO_PARITY = {"p": "+", "m": "-"}


# ---------------------------------------------------------------------------
# Doubled half-integers
# ---------------------------------------------------------------------------

def render_doubled(doubled: int) -> str:
    """Render a doubled quantum number as a slug token.

    ``4 -> "2"`` (integer), ``5 -> "5_2"`` (half-integer).
    """
    doubled = int(doubled)
    if doubled < 0:
        raise ValueError(f"Doubled quantum number must be non-negative, got {doubled}")
    if doubled % 2 == 0:
        return str(doubled // 2)
    return f"{doubled}_2"


def parse_doubled(token: str) -> int:
    """Inverse of :func:`render_doubled`.

    Rejects non-canonical forms such as ``"4_2"``, which would otherwise be a
    second spelling of ``"2"``.
    """
    match = _DOUBLED_TOKEN_RE.match(token)
    if match is None:
        raise ValueError(f"Cannot parse doubled quantum number from {token!r}")
    value, halves = match.groups()
    number = int(value)
    if halves:
        if number % 2 == 0:
            raise ValueError(
                f"Non-canonical slug token {token!r}: '_2' is only used for "
                f"half-integers, so the numerator must be odd."
            )
        return number
    return number * 2


def render_doubled_label(doubled: int) -> str:
    """Human-readable form of a doubled quantum number: ``4 -> "2"``, ``5 -> "5/2"``."""
    doubled = int(doubled)
    if doubled % 2 == 0:
        return str(doubled // 2)
    return f"{doubled}/2"


def parity_letter(parity: Any) -> str:
    """Normalise a parity declaration to the slug letter ``p`` or ``m``."""
    try:
        return _PARITY_TO_LETTER[parity]
    except (KeyError, TypeError):
        raise ValueError(
            f"Parity must be '+' or '-' (or +1/-1), got {parity!r}"
        ) from None


def parity_sign(parity: Any) -> str:
    """Normalise a parity declaration to ``'+'`` or ``'-'``."""
    return _LETTER_TO_PARITY[parity_letter(parity)]


# ---------------------------------------------------------------------------
# State slugs
# ---------------------------------------------------------------------------

def state_slug(J2: int, parity: Any, T2: int, index: int) -> str:
    """Build the slug for one state."""
    if int(index) < 1:
        raise ValueError(f"State index must be >= 1, got {index}")
    return (
        f"{render_doubled(J2)}{parity_letter(parity)}"
        f"-T{render_doubled(T2)}-n{int(index)}"
    )


def parse_state_slug(slug: str) -> dict[str, Any]:
    """Parse a state slug back into ``{J2, parity, T2, index}``."""
    match = STATE_SLUG_RE.match(slug)
    if match is None:
        raise ValueError(
            f"Cannot parse state slug {slug!r}. Expected the form "
            f"'2p-T1-n1' or '5_2p-T5_2-n1'."
        )
    spin, letter, isospin, index = match.groups()
    return {
        "J2": parse_doubled(spin),
        "parity": _LETTER_TO_PARITY[letter],
        "T2": parse_doubled(isospin),
        "index": int(index),
    }


def transition_slug(initial: str, final: str) -> str:
    """Join two state slugs into the symmetric transition form."""
    return f"{initial}{TRANSITION_SEP}{final}"


def parse_subject_slug(slug: str) -> dict[str, Any]:
    """Parse either a single-state slug or a transition pair.

    Returns ``{"kind": "state", "state": {...}}`` or
    ``{"kind": "transition", "initial": {...}, "final": {...}}``.
    """
    if TRANSITION_SEP in slug:
        initial, _, final = slug.partition(TRANSITION_SEP)
        return {
            "kind": "transition",
            "initial": parse_state_slug(initial),
            "final": parse_state_slug(final),
        }
    return {"kind": "state", "state": parse_state_slug(slug)}


# ---------------------------------------------------------------------------
# Observable slugs
# ---------------------------------------------------------------------------

def slugify_observable(name: str) -> str:
    """Make an observable name safe for a path segment.

    ``B(E2) -> BE2``, ``Mn/Mp -> Mn_over_Mp``, ``B(E2)/Qp^2 -> BE2_over_Qp2``.
    Ratios matter because ``/`` cannot appear in a path segment at all.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Observable name must be a non-empty string, got {name!r}")

    text = name.strip()
    text = text.replace("/", "_over_")
    for ch in "()[]{}^$\\,;:'\"!?*|<>":
        text = text.replace(ch, "")
    text = re.sub(r"[\s\-.]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")

    if not text or not _SAFE_SLUG_RE.match(text):
        raise ValueError(
            f"Observable name {name!r} does not reduce to a usable slug "
            f"(got {text!r}); declare an explicit slug in the observable registry."
        )
    return text


def _convention_token(key: str, value: Any) -> str:
    """Short slug token for one reference-convention entry."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    rendered = re.sub(r"[^A-Za-z0-9]+", "", str(value))
    if key == "evaluated_at_hOmega":
        return f"hw{rendered}"
    return f"{slugify_observable(key)}{rendered}"


def reference_suffix(
    reference: Mapping[str, Any],
    subject_nucleus: Optional[str] = None,
) -> str:
    """Build the ``_vs_...`` suffix that distinguishes reference choices.

    The nucleus is included only when it differs from the subject's, so an
    intra-nucleus excitation energy reads ``Eexc_vs_gs_hw16`` while a
    cross-nucleus relative energy reads ``Erel_vs_16C_gs``.

    Two results that differ only in their reference are different numbers, so
    the suffix is what keeps their ids from colliding.
    """
    parts: list[str] = ["vs"]

    ref_nucleus = reference.get("nucleus")
    if ref_nucleus and (
        subject_nucleus is None or str(ref_nucleus) != str(subject_nucleus)
    ):
        parts.append(slugify_observable(str(ref_nucleus)))

    alias = reference.get("alias")
    if alias:
        parts.append(slugify_observable(str(alias)))
    else:
        state = reference.get("state")
        if not state:
            raise ValueError(
                "Reference must declare either an 'alias' (e.g. 'gs') or a "
                "'state' block; got neither."
            )
        parts.append(
            state_slug(
                state["J2"], state["parity"], state["T2"], state.get("index", 1)
            )
        )

    convention = reference.get("convention") or {}
    for key in sorted(convention):
        parts.append(_convention_token(key, convention[key]))

    return "_".join(parts)


def observable_slug(
    name: str,
    reference: Optional[Mapping[str, Any]] = None,
    subject_nucleus: Optional[str] = None,
    explicit_slug: Optional[str] = None,
) -> str:
    """Build the observable path segment, including any reference suffix."""
    base = explicit_slug or slugify_observable(name)
    if not _SAFE_SLUG_RE.match(base):
        raise ValueError(
            f"Explicit observable slug {base!r} may only contain letters, "
            f"digits, and underscores."
        )
    if reference:
        return f"{base}_{reference_suffix(reference, subject_nucleus)}"
    return base


# ---------------------------------------------------------------------------
# Result ids
# ---------------------------------------------------------------------------

def build_result_id(
    nucleus: str,
    subject_slug: str,
    observable_slug_value: str,
    run_stamp: str,
) -> str:
    """Assemble ``{nucleus}/{state}/{observable}/{run_stamp}``."""
    for segment, label in (
        (nucleus, "nucleus"),
        (subject_slug, "subject slug"),
        (observable_slug_value, "observable slug"),
        (run_stamp, "run stamp"),
    ):
        if not segment or "/" in str(segment):
            raise ValueError(
                f"Result id {label} must be a non-empty segment without '/', "
                f"got {segment!r}"
            )
    return f"{nucleus}/{subject_slug}/{observable_slug_value}/{run_stamp}"


def family_of(result_id: str) -> str:
    """The grouping key: everything except the run stamp."""
    parts = result_id.split("/")
    if len(parts) != 4:
        raise ValueError(
            f"Result id must have 4 segments "
            f"(nucleus/state/observable/run_stamp), got {result_id!r}"
        )
    return "/".join(parts[:3])


def parse_result_id(result_id: str) -> dict[str, Any]:
    """Split a result id into its parts, parsing the subject slug."""
    parts = result_id.split("/")
    if len(parts) != 4:
        raise ValueError(
            f"Result id must have 4 segments "
            f"(nucleus/state/observable/run_stamp), got {result_id!r}"
        )
    nucleus, subject, observable, run_stamp = parts
    return {
        "nucleus": nucleus,
        "subject_slug": subject,
        "subject": parse_subject_slug(subject),
        "observable_slug": observable,
        "run_stamp": run_stamp,
        "family": "/".join(parts[:3]),
    }


def id_to_relative_path(result_id: str) -> str:
    """Bundle directory path relative to ``bundles/``.

    Identical to the id, since every segment is already path-safe.
    """
    # Validate before handing the string to a filesystem call.
    parse_result_id(result_id)
    return result_id


def sanitize_run_stamp(text: str) -> str:
    """Reduce a timestamp string to a safe, sortable path segment."""
    cleaned = re.sub(r"[^A-Za-z0-9_\-]+", "-", str(text)).strip("-")
    if not cleaned:
        raise ValueError(f"Run stamp {text!r} does not reduce to a usable segment")
    return cleaned


def declared_states_are_unique(
    declarations: Sequence[tuple[str, str, str, str]],
) -> list[str]:
    """Find identity collisions among per-sheet declarations.

    Each entry is ``(sheet, nucleus, subject_slug, observable_slug)``. Two sheets
    resolving to the same last three values would produce the same result id and
    silently overwrite one another's bundle, so this returns a human-readable
    message per collision.
    """
    seen: dict[tuple[str, str, str], list[str]] = {}
    for sheet, nucleus, subject, observable in declarations:
        seen.setdefault((nucleus, subject, observable), []).append(sheet)

    problems: list[str] = []
    for (nucleus, subject, observable), sheets in seen.items():
        if len(sheets) > 1:
            problems.append(
                f"Sheets {sorted(sheets)} all resolve to "
                f"{nucleus}/{subject}/{observable}; they would share one result "
                f"id and overwrite each other's bundle."
            )
    return problems
