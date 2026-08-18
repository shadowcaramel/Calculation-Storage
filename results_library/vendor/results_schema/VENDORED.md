# Vendored copy

Byte-identical copy of `results_schema/` from the pipeline repository.
Do not edit these files here. Change the originals, then run:

    python -m results_library.sync_schema --source <pipeline>/results_schema

The two repositories share the on-disk schema, not a Python import.
Compatibility is guarded by `schema_version` and `FIELDS.md`.
