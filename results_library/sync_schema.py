"""
Refresh the vendored copy of the result schema.

This repository carries a byte-identical copy of the pipeline's
``results_schema`` package under ``vendor/``. The on-disk schema, not a Python
import, is the boundary between the two repositories.

After changing anything in the pipeline's ``results_schema/``:

    python -m results_library.sync_schema --source "G:/My Drive/!ML/2026 rework/results_schema"

Byte-identical copies keep the sync trivial and make drift obvious in a diff.
``schema_version`` and ``FIELDS.md`` are what actually guard compatibility.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

PACKAGE = "results_schema"
FILES = (
    "__init__.py",
    "nuclides.py",
    "slugs.py",
    "labels.py",
    "identity.py",
    "models.py",
    "FIELDS.md",
)

ENV_VAR = "RESULTS_SCHEMA_SOURCE"


def vendor_dir() -> Path:
    return Path(__file__).resolve().parent / "vendor" / PACKAGE


def source_dir(explicit: Optional[Path] = None) -> Optional[Path]:
    """Locate the pipeline's live ``results_schema`` package."""
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env)
    return None


def sync(check_only: bool = False, source: Optional[Path] = None) -> int:
    """Copy schema files into ``vendor/``. Returns the number of stale files."""
    source_path = source_dir(source)
    target = vendor_dir()

    if source_path is None:
        print(
            "No schema source given. Pass --source <pipeline>/results_schema "
            f"or set {ENV_VAR}.",
            file=sys.stderr,
        )
        return -1

    if not source_path.is_dir():
        print(f"Source package not found: {source_path}", file=sys.stderr)
        return -1

    target.mkdir(parents=True, exist_ok=True)
    stale = 0

    for name in FILES:
        src = source_path / name
        dst = target / name
        if not src.exists():
            print(f"  missing in source: {name}", file=sys.stderr)
            stale += 1
            continue

        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            continue

        stale += 1
        if check_only:
            print(f"  stale: {name}")
        else:
            shutil.copy2(src, dst)
            print(f"  updated: {name}")

    marker = target / "VENDORED.md"
    if not check_only:
        marker.write_text(
            "# Vendored copy\n\n"
            f"Byte-identical copy of `{PACKAGE}/` from the pipeline repository.\n"
            "Do not edit these files here. Change the originals, then run:\n\n"
            "    python -m results_library.sync_schema "
            "--source <pipeline>/results_schema\n\n"
            "The two repositories share the on-disk schema, not a Python import.\n"
            "Compatibility is guarded by `schema_version` and `FIELDS.md`.\n",
            encoding="utf-8",
        )

    if check_only:
        print("vendor copy is up to date" if stale == 0 else f"{stale} stale file(s)")
    else:
        print(f"vendor copy synced ({stale} file(s) changed)")
    return stale


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report stale files without copying (exit code 1 if any)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="path to the pipeline's results_schema package "
        f"(or set {ENV_VAR})",
    )
    args = parser.parse_args(argv)
    stale = sync(check_only=args.check, source=args.source)
    if stale < 0:
        return 2
    return 1 if (args.check and stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
