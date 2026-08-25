"""v1 -> v2: selection sets live in a hashed subfolder of the run folder."""

from __future__ import annotations

from typing import Any, Dict

from results_library.migrations import register


def rewrite_v1_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Rewrite a v1 record's id and attach ``cohort_hash``.

    Physical folder moves are the CLI's job; this function is the in-memory
    counterpart so a half-migrated library still catalogs.
    """
    from results_schema.slugs import family_of, v2_id_from_v1

    record = dict(record)
    variant_data = dict(record.get("variant") or {})
    cohort_hash = variant_data.get("cohort_hash")
    variant_hash = variant_data.get("variant_hash")
    selection_set = variant_data.get("selection_set")

    try:
        from results_schema.models import Variant

        hashed = Variant.model_validate(variant_data).with_hashes()
        cohort_hash = hashed.cohort_hash
        variant_hash = hashed.variant_hash
        selection_set = hashed.selection_set
    except Exception:
        pass

    if cohort_hash:
        variant_data["cohort_hash"] = cohort_hash
    if variant_hash:
        variant_data["variant_hash"] = variant_hash
    record["variant"] = variant_data

    old_id = str(record.get("id") or "")
    new_id = v2_id_from_v1(
        old_id,
        selection_set=selection_set if isinstance(selection_set, str) else None,
        cohort_hash=cohort_hash if isinstance(cohort_hash, str) else None,
        variant_hash=variant_hash if isinstance(variant_hash, str) else None,
    )
    record["id"] = new_id
    try:
        record["family"] = family_of(new_id)
    except ValueError:
        pass
    return record


@register(1)
def migrate_v1_to_v2(record: Dict[str, Any]) -> Dict[str, Any]:
    return rewrite_v1_record(record)
