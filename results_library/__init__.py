"""
Results library tooling: catalog builder and views.

This package is the *reader* side of the results storage system. It never
imports pipeline code. The only thing shared with the pipeline is the on-disk
schema, guarded by ``schema_version`` and documented in ``FIELDS.md``.

A byte-identical copy of the schema helpers is vendored under ``vendor/`` so
this repository stays self-contained. Refresh it from the pipeline originals:

    python -m results_library.sync_schema --source <pipeline>/results_schema
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.append(str(_VENDOR))

#: Highest ``schema_version`` this tooling understands. A record above this is
#: reported by the lint pass instead of being silently misread.
SUPPORTED_SCHEMA_VERSION = 2

__all__ = ["SUPPORTED_SCHEMA_VERSION"]
