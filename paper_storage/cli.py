"""
Command line for the paper site.

    python -m paper_storage build --library "G:/Shared drives/Calculation results/Calculation storage"
    python -m paper_storage build --bibliography path/to/my_publications.bib

The calculation catalogue is a different command. Pass ``--with-papers`` there
when both sites should be written together.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

ENV_LIBRARY = "RESULTS_LIBRARY"
ENV_BIBLIOGRAPHY = "PAPER_BIBLIOGRAPHY"


def resolve_library(args: argparse.Namespace) -> Path:
    candidate = getattr(args, "library", None) or os.environ.get(ENV_LIBRARY)
    if not candidate:
        print(
            "No library path given. Use --library or set RESULTS_LIBRARY.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    path = Path(candidate)
    if not path.exists():
        print(f"Library path does not exist: {path}", file=sys.stderr)
        raise SystemExit(2)
    return path


def resolve_bibliography(args: argparse.Namespace) -> Optional[Path]:
    candidate = getattr(args, "bibliography", None) or os.environ.get(ENV_BIBLIOGRAPHY)
    if not candidate:
        return None
    path = Path(candidate)
    if not path.is_file():
        print(f"Bibliography not found, continuing without it: {path}", file=sys.stderr)
        return None
    return path


def command_build(args: argparse.Namespace) -> int:
    from paper_storage.build import build_papers

    library = resolve_library(args)
    result = build_papers(library, bibliography=resolve_bibliography(args))
    for issue in result.issues:
        print(f"  {issue}")
    if not result.ok:
        print("Paper storage build failed.", file=sys.stderr)
        return 1
    print(f"Papers: {result.site / 'index.html'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--library", help="path to the shared library root")
    shared.add_argument(
        "--bibliography",
        help="path to my_publications.bib (or set PAPER_BIBLIOGRAPHY)",
    )
    shared.add_argument("--verbose", "-v", action="store_true")
    parser = argparse.ArgumentParser(
        prog="paper_storage",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[shared],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="write the paper site", parents=[shared])
    build.set_defaults(func=command_build)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)
