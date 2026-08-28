"""
The result contract: pydantic models for one stored calculation result.

These models define ``result.json``, the durable source of truth for a result.
Design rules that keep records readable a year from now:

* **Self-describing and versioned.** Every record carries ``schema_version``
  plus provenance, so an old number can still be interpreted.
* **Additive and nullable by default.** Models accept unknown extra fields and
  round-trip them untouched, so a record written by newer code stays readable by
  older code and vice versa. New features add optional fields; old records
  simply lack them.
* **Method stored next to value.** ``uncertainty_method``,
  ``homega_aggregation`` and the observable ``direction`` travel with the number
  so values produced months apart are never silently compared.

Only this module needs pydantic. The identity, slug, label, and nuclide helpers
are stdlib-only so the early config check can run in a bare environment.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from results_schema.identity import validate_state_declaration
from results_schema.slugs import (
    DEFAULT_LINEAGE,
    build_result_id,
    build_selection_stamp,
    family_of,
    normalize_lineage,
    parity_sign,
    state_slug,
    transition_slug,
)

SCHEMA_VERSION = 2

#: Curation states. ``probing`` is the default for every auto-captured run;
#: promotion to ``working`` or ``published`` is always manual.
STATUSES = ("probing", "working", "published", "superseded")

Status = Literal["probing", "working", "published", "superseded"]
Lineage = Literal["modern", "legacy"]


class _Base(BaseModel):
    """Common configuration: preserve unknown fields for forward compatibility."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

class StateRecord(_Base):
    """One nuclear state, with spin and isospin stored doubled.

    Doubling keeps them integers, so no fractions or floats ever enter an
    identity: ``J2 = 5`` means J = 5/2, ``T2 = 4`` means T = 2.
    """

    J2: int = Field(..., ge=0, description="Twice the total angular momentum")
    parity: Literal["+", "-"]
    T2: int = Field(..., ge=0, description="Twice the isospin; always explicit")
    index: int = Field(1, ge=1, description="n, ordinal among states of the same J^pi")

    @field_validator("parity", mode="before")
    @classmethod
    def _normalise_parity(cls, value: Any) -> str:
        return parity_sign(value)

    @property
    def slug(self) -> str:
        return state_slug(self.J2, self.parity, self.T2, self.index)


class StateRef(_Base):
    """A state together with the nucleus it belongs to."""

    nucleus: str
    state: StateRecord

    @model_validator(mode="after")
    def _check_against_nucleus(self) -> "StateRef":
        problems = validate_state_declaration(
            self.nucleus,
            self.state.J2,
            self.state.parity,
            self.state.T2,
            self.state.index,
        )
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def slug(self) -> str:
        return self.state.slug


class Subject(_Base):
    """What the result is about: a single state, or a transition between two.

    Cross-nucleus quantities are *not* modelled here as a pair. A relative energy
    has a primary subject and a reference, which is asymmetric, so the subject
    stays a single state and the reference lives in :class:`Reference`.
    """

    kind: Literal["state", "transition"]
    nucleus: Optional[str] = None
    state: Optional[StateRecord] = None
    initial: Optional[StateRef] = None
    final: Optional[StateRef] = None

    @model_validator(mode="after")
    def _check_shape(self) -> "Subject":
        if self.kind == "state":
            if self.nucleus is None or self.state is None:
                raise ValueError(
                    "Subject kind='state' requires 'nucleus' and 'state'"
                )
            problems = validate_state_declaration(
                self.nucleus,
                self.state.J2,
                self.state.parity,
                self.state.T2,
                self.state.index,
            )
            if problems:
                raise ValueError("; ".join(problems))
        else:
            if self.initial is None or self.final is None:
                raise ValueError(
                    "Subject kind='transition' requires 'initial' and 'final'"
                )
            if self.initial.nucleus != self.final.nucleus:
                raise ValueError(
                    f"Transition endpoints are in different nuclei "
                    f"({self.initial.nucleus} and {self.final.nucleus}). Model a "
                    f"cross-nucleus quantity as a single subject plus a reference "
                    f"instead of a transition."
                )
        return self

    @property
    def nucleus_name(self) -> str:
        if self.kind == "state":
            return str(self.nucleus)
        return str(self.initial.nucleus)  # type: ignore[union-attr]

    @property
    def slug(self) -> str:
        if self.kind == "state":
            return self.state.slug  # type: ignore[union-attr]
        return transition_slug(
            self.initial.slug,  # type: ignore[union-attr]
            self.final.slug,  # type: ignore[union-attr]
        )

    @classmethod
    def single(cls, nucleus: str, state: StateRecord) -> "Subject":
        return cls(kind="state", nucleus=nucleus, state=state)

    @classmethod
    def transition(
        cls, nucleus: str, initial: StateRecord, final: StateRecord
    ) -> "Subject":
        return cls(
            kind="transition",
            initial=StateRef(nucleus=nucleus, state=initial),
            final=StateRef(nucleus=nucleus, state=final),
        )


class Reference(_Base):
    """What a relative quantity is measured against.

    Needed for cross-nucleus quantities *and* for ordinary excitation energies,
    because the reference choice changes the number: the same state referenced to
    the ground state at one hOmega or another yields different values, and those
    must not collide.
    """

    nucleus: Optional[str] = None
    state: Optional[StateRecord] = None
    alias: Optional[str] = None
    convention: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_shape(self) -> "Reference":
        if self.state is None and not self.alias:
            raise ValueError(
                "Reference needs either 'alias' (e.g. 'gs') or a 'state' block"
            )
        if self.state is not None and self.nucleus:
            problems = validate_state_declaration(
                self.nucleus,
                self.state.J2,
                self.state.parity,
                self.state.T2,
                self.state.index,
            )
            if problems:
                raise ValueError("; ".join(problems))
        return self

    def as_slug_input(self) -> Dict[str, Any]:
        """Mapping shape expected by :func:`results_schema.slugs.reference_suffix`."""
        data: Dict[str, Any] = {}
        if self.nucleus:
            data["nucleus"] = self.nucleus
        if self.alias:
            data["alias"] = self.alias
        if self.state is not None:
            data["state"] = self.state.model_dump()
        if self.convention:
            data["convention"] = dict(self.convention)
        return data


class Observable(_Base):
    """The measured quantity, with its display forms and any convention.

    ``direction`` matters for transition strengths: B(E2) up and down differ by
    ``(2J_f+1)/(2J_i+1)``, so an unlabelled value is ambiguous.
    """

    slug: str
    name: Optional[str] = None
    latex: Optional[str] = None
    unicode: Optional[str] = None
    units: Optional[str] = None
    direction: Optional[Literal["up", "down"]] = None

    @property
    def display(self) -> str:
        return self.name or self.slug


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

class Computed(_Base):
    """The extrapolated number and its uncertainty.

    Mirrors what ``_compute_output_stats`` already produces in
    ``postprocessing/calculation_summary.py``; nothing is recomputed here.
    """

    median: float
    Q1: Optional[float] = None
    Q3: Optional[float] = None
    err_low: Optional[float] = None
    err_high: Optional[float] = None
    IQR: Optional[float] = None
    N_models: Optional[int] = None
    Nmax_final: Optional[float] = None
    uncertainty_method: Optional[str] = None
    homega_aggregation: Optional[str] = None
    KDE_mode: Optional[float] = None
    HDR_low: Optional[float] = None
    HDR_high: Optional[float] = None


class Variant(_Base):
    """The setup that produced this number.

    Exploratory work varies bounds, selection sets, filters and reference
    conventions over the same physics question, so this block is what makes a
    scan comparable and keeps near-identical runs distinguishable.
    """

    bounds: Dict[str, Any] = Field(default_factory=dict)
    selection_set: Optional[str] = None
    filter_criteria: List[str] = Field(default_factory=list)
    reference_convention: Dict[str, Any] = Field(default_factory=dict)
    config_name: Optional[str] = None
    potential: Optional[str] = None
    variant_hash: Optional[str] = None
    cohort_hash: Optional[str] = None

    def _digest(self, exclude: set[str]) -> str:
        payload = self.model_dump(exclude=exclude, exclude_none=True)
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]

    def compute_hash(self) -> str:
        """Short digest of the full setup, including the selection set."""
        return self._digest({"variant_hash", "cohort_hash"})

    def compute_cohort_hash(self) -> str:
        """Digest of the trained ensemble, shared by every selection set.

        Excludes ``selection_set`` and ``filter_criteria`` so ``final`` and
        ``all_models`` land under the same parent folder.
        """
        return self._digest(
            {"variant_hash", "cohort_hash", "selection_set", "filter_criteria"}
        )

    def with_hashes(self) -> "Variant":
        return self.model_copy(
            update={
                "cohort_hash": self.compute_cohort_hash(),
                "variant_hash": self.compute_hash(),
            }
        )

    def with_hash(self) -> "Variant":
        """Backward-compatible alias for :meth:`with_hashes`."""
        return self.with_hashes()


class StoredFile(_Base):
    """A file copied into the library (content-addressed under ``sources/``)."""

    name: str
    sha256: str
    path: str


class Provenance(_Base):
    """Where the number came from.

    ``source_workbook`` and ``source_sheet`` are taken from the config paths the
    pipeline already uses; nothing is scraped from inside the workbook.
    ``config_snapshot`` is the frozen config copied into this bundle.
    ``source_files`` are the collaborator dumps; ``source_file`` is the extracted
    pivot used for Phase 0 conversion.
    """

    code_version: Optional[str] = None
    created_at: Optional[str] = None
    run_dir: Optional[str] = None
    config_snapshot: Optional[str] = None
    source_workbook: Optional[str] = None
    source_sheet: Optional[str] = None
    source_file: Optional[StoredFile] = None
    source_files: List[StoredFile] = Field(default_factory=list)
    prepared_file: Optional[StoredFile] = None
    provenance_check: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

class ResultRecord(_Base):
    """One stored result: ``result.json`` inside a bundle."""

    schema_version: int = SCHEMA_VERSION
    id: str
    family: str
    subject: Subject
    reference: Optional[Reference] = None
    observable: Observable
    computed: Computed
    variant: Variant = Field(default_factory=Variant)
    provenance: Provenance = Field(default_factory=Provenance)
    status: Status = "probing"
    lineage: Lineage = "modern"
    available: List[str] = Field(default_factory=list)
    artifacts: Dict[str, str] = Field(default_factory=dict)
    column_labels: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @field_validator("lineage", mode="before")
    @classmethod
    def _normalise_lineage(cls, value: Any) -> str:
        if value is None or (isinstance(value, str) and not str(value).strip()):
            return DEFAULT_LINEAGE
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @model_validator(mode="after")
    def _check_family(self) -> "ResultRecord":
        expected = family_of(self.id)
        if self.family != expected:
            raise ValueError(
                f"family {self.family!r} does not match id {self.id!r} "
                f"(expected {expected!r})"
            )
        return self

    # -- construction --------------------------------------------------

    @classmethod
    def build(
        cls,
        subject: Subject,
        observable: Observable,
        computed: Computed,
        run_stamp: str,
        observable_path_slug: Optional[str] = None,
        reference: Optional[Reference] = None,
        variant: Optional[Variant] = None,
        provenance: Optional[Provenance] = None,
        available: Optional[List[str]] = None,
        artifacts: Optional[Mapping[str, str]] = None,
        column_labels: Optional[Mapping[str, Mapping[str, Any]]] = None,
        status: Status = "probing",
        lineage: Lineage = "modern",
        selection_stamp: Optional[str] = None,
    ) -> "ResultRecord":
        """Assemble a record, deriving ``id`` and ``family`` from the identity."""
        path_slug = observable_path_slug or observable.slug
        variant = (variant or Variant()).with_hashes()
        if selection_stamp is None:
            selection_stamp = build_selection_stamp(
                variant.selection_set, variant.variant_hash
            )
        result_id = build_result_id(
            subject.nucleus_name,
            subject.slug,
            path_slug,
            run_stamp,
            selection_stamp,
        )
        return cls(
            id=result_id,
            family=family_of(result_id),
            subject=subject,
            reference=reference,
            observable=observable,
            computed=computed,
            variant=variant,
            provenance=provenance or Provenance(),
            status=status,
            lineage=normalize_lineage(lineage),  # type: ignore[arg-type]
            available=list(available or []),
            artifacts=dict(artifacts or {}),
            column_labels={
                str(k): dict(v) for k, v in dict(column_labels or {}).items()
            },
        )

    # -- serialisation -------------------------------------------------

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            indent=indent,
            ensure_ascii=False,
        )

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def read_json(cls, path: Path) -> "ResultRecord":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)


def utc_now_iso() -> str:
    """Timestamp for ``Provenance.created_at``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
