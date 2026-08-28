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
    mathtext_to_unicode,
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
from results_schema.nuclides import Nuclide, nucleus_sort_key, parse_nuclide
from results_schema.slugs import (
    DEFAULT_LINEAGE,
    LINEAGES,
    TRANSITION_SEP,
    build_result_id,
    build_selection_stamp,
    bundle_dir_segments,
    declared_states_are_unique,
    family_of,
    format_run_date_label,
    lineage_prefix,
    normalize_lineage,
    observable_slug,
    parity_sign,
    parse_result_id,
    parse_run_datetime,
    parse_state_slug,
    parse_subject_slug,
    reference_suffix,
    run_datetime_sort_key,
    sanitize_run_stamp,
    slugify_observable,
    split_run_stamp,
    state_slug,
    transition_slug,
    v2_id_from_v1,
)

#: Bumped only when a stored record's meaning changes; see FIELDS.md.
SCHEMA_VERSION = 2

__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_LINEAGE",
    "LINEAGES",
    "TRANSITION_SEP",
    "Nuclide",
    "SheetIdentity",
    "StateDeclaration",
    "axis_latex",
    "axis_unicode",
    "build_result_id",
    "build_selection_stamp",
    "bundle_dir_segments",
    "build_state_declaration",
    "collect_column_labels",
    "column_label_from_plot_entry",
    "declared_states_are_unique",
    "family_of",
    "format_run_date_label",
    "format_value_with_uncertainty",
    "lineage_prefix",
    "mathtext_to_unicode",
    "normalize_lineage",
    "nuclide_latex",
    "nuclide_unicode",
    "nucleus_sort_key",
    "observable_unicode",
    "observable_slug",
    "parity_sign",
    "parse_nuclide",
    "parse_result_id",
    "parse_run_datetime",
    "parse_state_slug",
    "parse_subject_slug",
    "reference_suffix",
    "reference_unicode",
    "resolve_sheet_identity",
    "result_unicode",
    "run_datetime_sort_key",
    "sanitize_run_stamp",
    "split_run_stamp",
    "setup_label",
    "slugify_observable",
    "state_latex",
    "state_slug",
    "state_unicode",
    "subject_latex",
    "subject_unicode",
    "transition_slug",
    "v2_id_from_v1",
    "validate_reference_declaration",
    "validate_state_declaration",
]
