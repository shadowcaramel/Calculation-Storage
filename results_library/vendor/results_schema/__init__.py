"""
The result contract shared by the pipeline and the results library.

Layering note: everything exported here is stdlib-only, so the early config
check can validate a declaration in an environment without pydantic. The
pydantic models live in :mod:`results_schema.models` and must be imported
explicitly.
"""

from __future__ import annotations

from results_schema.identity import (
    SheetIdentity,
    StateDeclaration,
    build_state_declaration,
    resolve_sheet_identity,
    validate_reference_declaration,
    validate_state_declaration,
)
from results_schema.labels import (
    axis_latex,
    axis_unicode,
    collect_column_labels,
    column_label_from_plot_entry,
    format_value_with_uncertainty,
    nuclide_latex,
    nuclide_unicode,
    observable_unicode,
    reference_unicode,
    result_unicode,
    setup_label,
    state_latex,
    state_unicode,
    subject_latex,
    subject_unicode,
)
from results_schema.nuclides import Nuclide, parse_nuclide
from results_schema.slugs import (
    TRANSITION_SEP,
    build_result_id,
    declared_states_are_unique,
    family_of,
    observable_slug,
    parity_sign,
    parse_result_id,
    parse_state_slug,
    parse_subject_slug,
    reference_suffix,
    sanitize_run_stamp,
    slugify_observable,
    state_slug,
    transition_slug,
)

#: Bumped only when a stored record's meaning changes; see FIELDS.md.
SCHEMA_VERSION = 1

__all__ = [
    "SCHEMA_VERSION",
    "TRANSITION_SEP",
    "Nuclide",
    "SheetIdentity",
    "StateDeclaration",
    "axis_latex",
    "axis_unicode",
    "build_result_id",
    "build_state_declaration",
    "collect_column_labels",
    "column_label_from_plot_entry",
    "declared_states_are_unique",
    "family_of",
    "format_value_with_uncertainty",
    "nuclide_latex",
    "nuclide_unicode",
    "observable_unicode",
    "observable_slug",
    "parity_sign",
    "parse_nuclide",
    "parse_result_id",
    "parse_state_slug",
    "parse_subject_slug",
    "reference_suffix",
    "reference_unicode",
    "resolve_sheet_identity",
    "result_unicode",
    "sanitize_run_stamp",
    "setup_label",
    "slugify_observable",
    "state_latex",
    "state_slug",
    "state_unicode",
    "subject_latex",
    "subject_unicode",
    "transition_slug",
    "validate_reference_declaration",
    "validate_state_declaration",
]
