"""
Command line interface for the results library.

    python -m results_library.cli build   --library "G:/Shared drives/Calculation results/Calculation storage"
    python -m results_library.cli catalog --library ...
    python -m results_library.cli site    --library ...
    python -m results_library.cli excel   --library ...
    python -m results_library.cli lint    --library ...
    python -m results_library.cli serve   --library ...
    python -m results_library.cli migrate-selection-folders --library ...
    python -m results_library.cli migrate-lineage-folders --library ...

``build`` is the everyday command: it rebuilds the catalog, the site, and the
workbook from scratch. There is no incremental state, so nothing can end up
half-updated and a rebuild is always safe.

The library path can also come from ``RESULTS_LIBRARY`` in the environment, or
from a pipeline ``config.toml`` via ``--config``, so it need not be retyped.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tomllib
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ENV_VAR = "RESULTS_LIBRARY"


# ---------------------------------------------------------------------------
# Library location
# ---------------------------------------------------------------------------

def _library_from_config(config_path: Path) -> Optional[str]:
    try:
        with open(config_path, "rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"Cannot read {config_path}: {exc}", file=sys.stderr)
        return None
    return (config.get("results_library") or {}).get("path")


def resolve_library(args: argparse.Namespace) -> Path:
    """Find the library root, or exit with an actionable message."""
    candidate = getattr(args, "library", None)

    if not candidate and getattr(args, "config", None):
        candidate = _library_from_config(Path(args.config))

    if not candidate:
        candidate = os.environ.get(ENV_VAR)

    if not candidate:
        print(
            "No library path given. Use one of:\n"
            "  --library \"G:/Shared drives/Calculation results/Calculation storage\"\n"
            "  --config path/to/config.toml   (reads [results_library].path)\n"
            f"  set {ENV_VAR} in the environment",
            file=sys.stderr,
        )
        raise SystemExit(2)

    path = Path(candidate)
    if not path.exists():
        print(f"Library path does not exist: {path}", file=sys.stderr)
        raise SystemExit(2)
    return path


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def command_catalog(args: argparse.Namespace) -> int:
    from results_library.catalog import build_catalog, write_catalog

    library = resolve_library(args)
    frame, scan = build_catalog(library)
    paths = write_catalog(frame, library)

    print(f"Scanned {len(scan.records)} bundle(s) under {library / 'bundles'}")
    if scan.unreadable:
        print(f"  {len(scan.unreadable)} unreadable; run 'lint' for details")
    migrated = sum(1 for r in scan.records if r.migrations_applied)
    if migrated:
        print(f"  {migrated} record(s) upgraded on read")
    print(f"Catalog: {paths['parquet']}")
    print(f"Catalog: {paths['sqlite']}")
    return 0


def command_site(args: argparse.Namespace) -> int:
    from results_library.catalog import build_catalog
    from results_library.views.site import build_site

    library = resolve_library(args)
    frame, _ = build_catalog(library)
    build_site(library, frame)
    print(f"Site: {library / 'index.html'}  (legacy: {library / 'legacy.html'})")
    return 0


def command_excel(args: argparse.Namespace) -> int:
    from results_library.catalog import build_catalog
    from results_library.views.excel import build_workbook

    library = resolve_library(args)
    frame, _ = build_catalog(library)
    try:
        path = build_workbook(library, frame, include_probing=args.include_probing)
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Workbook: {path}")
    return 0


def command_lint(args: argparse.Namespace) -> int:
    from results_library.catalog import scan_bundles
    from results_library.lint import lint_library, summarise

    library = resolve_library(args)
    scan = scan_bundles(library)
    issues = lint_library(library, scan)
    counts = summarise(issues)

    print(f"Checked {len(scan.records)} bundle(s) in {library}")
    for issue in issues:
        print(f"  {issue}")

    print(
        f"{counts.get('error', 0)} error(s), "
        f"{counts.get('warning', 0)} warning(s), "
        f"{counts.get('info', 0)} note(s)"
    )
    # Errors mean something in the library is wrong, which is worth a non-zero
    # exit so this can be used in a check script.
    return 1 if counts.get("error", 0) else 0


def command_build(args: argparse.Namespace) -> int:
    from results_library.catalog import build_catalog, write_catalog
    from results_library.lint import lint_library, summarise
    from results_library.views.excel import build_workbook
    from results_library.views.site import build_site

    library = resolve_library(args)

    frame, scan = build_catalog(library)
    paths = write_catalog(frame, library)
    print(f"Catalog: {len(frame)} result(s) -> {paths['parquet'].name}, {paths['sqlite'].name}")

    build_site(library, frame)
    print(f"Site:    {library / 'index.html'}  (legacy: {library / 'legacy.html'})")

    if not args.no_excel:
        try:
            workbook = build_workbook(library, frame, include_probing=args.include_probing)
            print(f"Excel:   {workbook.name}")
        except PermissionError as exc:
            print(f"Excel:   skipped ({exc})", file=sys.stderr)

    issues = lint_library(library, scan)
    counts = summarise(issues)
    if counts.get("error") or counts.get("warning"):
        print(
            f"Lint:    {counts.get('error', 0)} error(s), "
            f"{counts.get('warning', 0)} warning(s) "
            f"-- run 'lint' for details"
        )
    else:
        print("Lint:    clean")
    return 0


def command_migrate_selection_folders(args: argparse.Namespace) -> int:
    from results_library.migrate_paths import migrate_selection_folders

    library = resolve_library(args)
    report = migrate_selection_folders(library, dry_run=args.dry_run)
    verb = "Would move" if args.dry_run else "Moved"
    print(f"{verb} {len(report.moved)} bundle(s) under {library / 'bundles'}")
    for item in report.moved:
        print(f"  {item.old_id}")
        print(f"    -> {item.new_id}")
    if report.rewritten_files:
        action = "Would update" if args.dry_run else "Updated"
        print(f"{action}: {', '.join(report.rewritten_files)}")
    if report.skipped:
        print(f"Skipped {len(report.skipped)}")
        if getattr(args, "verbose", False):
            for message in report.skipped:
                print(f"  {message}")
    if report.errors:
        print(f"{len(report.errors)} error(s)")
        for message in report.errors:
            print(f"  {message}")
        return 1
    return 0


def command_migrate_lineage_folders(args: argparse.Namespace) -> int:
    from results_library.migrate_lineage import migrate_lineage_folders

    library = resolve_library(args)
    report = migrate_lineage_folders(library, dry_run=args.dry_run)
    verb = "Would move" if args.dry_run else "Moved"
    print(f"{verb} {len(report.moved)} bundle(s) under {library / 'bundles'}")
    for item in report.moved:
        print(f"  {item.result_id}")
        print(f"    -> {item.new_dir.relative_to(library)}")
    if report.skipped:
        print(f"Skipped {len(report.skipped)}")
        if getattr(args, "verbose", False):
            for message in report.skipped:
                print(f"  {message}")
    if report.errors:
        print(f"{len(report.errors)} error(s)")
        for message in report.errors:
            print(f"  {message}")
        return 1
    return 0


def command_serve(args: argparse.Namespace) -> int:
    """Hand off to Datasette for a live, queryable view of the catalog."""
    from results_library.catalog import CATALOG_DB

    library = resolve_library(args)
    database = library / CATALOG_DB
    if not database.exists():
        print(
            f"No catalog database at {database}. Build it first:\n"
            f"  python -m results_library.cli catalog --library \"{library}\"",
            file=sys.stderr,
        )
        return 1

    try:
        from datasette.cli import cli as datasette_cli
    except ImportError:
        print(
            "Datasette is not installed. It gives an instant browsable, "
            "filterable view of the catalog with CSV/JSON export:\n"
            "  pip install datasette\n"
            f"then:\n  datasette \"{database}\"",
            file=sys.stderr,
        )
        return 1

    print(f"Serving {database} with Datasette on port {args.port}...")
    datasette_cli(
        ["serve", str(database), "--port", str(args.port)],
        standalone_mode=False,
    )
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    # Shared flags are attached to the top-level parser *and* every
    # subparser so both of these work:
    #   python -m results_library.cli --library PATH build
    #   python -m results_library.cli build --library PATH
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--library",
        default=argparse.SUPPRESS,
        help="path to the results library root",
    )
    shared.add_argument(
        "--config",
        default=argparse.SUPPRESS,
        help="pipeline config.toml to read [results_library].path from",
    )
    shared.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=argparse.SUPPRESS,
        help="show debug logging",
    )

    parser = argparse.ArgumentParser(
        prog="results_library",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[shared],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    everything = subparsers.add_parser(
        "build",
        help="rebuild catalog, site, and workbook (the everyday command)",
        parents=[shared],
    )
    everything.add_argument("--no-excel", action="store_true", help="skip the workbook")
    everything.add_argument(
        "--include-probing",
        action="store_true",
        help="include exploratory results in the workbook",
    )
    everything.set_defaults(func=command_build)

    catalog = subparsers.add_parser(
        "catalog", help="rebuild catalog.parquet and catalog.db", parents=[shared]
    )
    catalog.set_defaults(func=command_catalog)

    site = subparsers.add_parser(
        "site", help="rebuild the static HTML site", parents=[shared]
    )
    site.set_defaults(func=command_site)

    excel = subparsers.add_parser(
        "excel", help="rebuild the Excel workbook", parents=[shared]
    )
    excel.add_argument(
        "--include-probing",
        action="store_true",
        help="include exploratory results",
    )
    excel.set_defaults(func=command_excel)

    lint = subparsers.add_parser(
        "lint", help="check the library for inconsistencies", parents=[shared]
    )
    lint.set_defaults(func=command_lint)

    serve = subparsers.add_parser(
        "serve", help="serve the catalog with Datasette", parents=[shared]
    )
    serve.add_argument("--port", type=int, default=8001)
    serve.set_defaults(func=command_serve)

    migrate = subparsers.add_parser(
        "migrate-selection-folders",
        help="rewrite v1 four-segment bundles into v2 selection-set folders",
        parents=[shared],
    )
    migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned moves without touching the library",
    )
    migrate.set_defaults(func=command_migrate_selection_folders)

    migrate_lineage = subparsers.add_parser(
        "migrate-lineage-folders",
        help="move unprefixed bundles under bundles/modern or bundles/legacy",
        parents=[shared],
    )
    migrate_lineage.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned moves without touching the library",
    )
    migrate_lineage.set_defaults(func=command_migrate_lineage_folders)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
