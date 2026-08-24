"""
Hand-curated figures that span several stored results.

``comparisons.toml`` lives at the library root, is edited by hand, and is
**never** written by a catalog or site build. Drop image files under
``comparisons/`` and point at them from the TOML. The site only reads this
file; missing or malformed input yields no comparison page rather than
aborting the build.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Mapping

logger = logging.getLogger(__name__)

COMPARISONS_FILENAME = "comparisons.toml"


@dataclass(frozen=True)
class ComparisonFigure:
    """One multi-result figure declared in ``comparisons.toml``."""

    title: str
    file: str
    caption: str = ""
    results: List[str] = field(default_factory=list)


def comparisons_path(library_root: Path) -> Path:
    return Path(library_root) / COMPARISONS_FILENAME


def load_comparisons(library_root: Path) -> List[ComparisonFigure]:
    """Read comparison figures, or an empty list when nothing is declared."""
    path = comparisons_path(library_root)
    if not path.exists():
        return []
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return []

    figures: List[ComparisonFigure] = []
    for entry in data.get("figure") or []:
        if not isinstance(entry, Mapping):
            continue
        title = str(entry.get("title") or "").strip()
        file = str(entry.get("file") or "").strip().replace("\\", "/")
        if not title or not file:
            continue
        results = [
            str(item).strip()
            for item in (entry.get("results") or [])
            if str(item).strip()
        ]
        figures.append(
            ComparisonFigure(
                title=title,
                file=file,
                caption=str(entry.get("caption") or "").strip(),
                results=results,
            )
        )
    return figures


def figures_for_result(
    figures: Iterable[ComparisonFigure], result_id: str
) -> List[ComparisonFigure]:
    wanted = str(result_id)
    return [figure for figure in figures if wanted in figure.results]


def figures_for_nucleus(
    figures: Iterable[ComparisonFigure], nucleus: str
) -> List[ComparisonFigure]:
    prefix = f"{nucleus}/"
    return [
        figure
        for figure in figures
        if any(item == nucleus or item.startswith(prefix) for item in figure.results)
    ]
