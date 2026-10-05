"""
Loose comparison between a printed cell and a stored median.

``direct`` warns when the two disagree past the last digit printed in the
paper. ``derived`` does not: the printed value may be an extrapolated energy
minus a threshold, or some other adjustment, and the link's note says so.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

_NUMBER = re.compile(r"[-+]?\d+(?:\.(\d+))?")


def result_json_path(library_root: Path, result_id: str) -> Optional[Path]:
    """Find ``result.json`` for an id under ``bundles/modern`` or ``bundles/legacy``."""
    parts = [part for part in str(result_id).replace("\\", "/").split("/") if part]
    if not parts:
        return None
    bundles = Path(library_root) / "bundles"
    for lineage in ("modern", "legacy"):
        path = bundles.joinpath(lineage, *parts, "result.json")
        if path.is_file():
            return path
    bare = bundles.joinpath(*parts, "result.json")
    if bare.is_file():
        return bare
    return None


def bundle_median(library_root: Path, result_id: str) -> Optional[float]:
    """The stored central value, or ``None`` when the bundle is absent."""
    path = result_json_path(library_root, result_id)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    computed = data.get("computed") or {}
    if not isinstance(computed, dict):
        return None
    median = computed.get("median")
    if isinstance(median, bool) or not isinstance(median, (int, float)):
        return None
    return float(median)


def bundle_potential(library_root: Path, result_id: str) -> Optional[str]:
    """The nucleon-nucleon interaction stored on the bundle, if any."""
    path = result_json_path(library_root, result_id)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    variant = data.get("variant") or {}
    if not isinstance(variant, dict):
        return None
    potential = variant.get("potential")
    if not isinstance(potential, str) or not potential.strip():
        return None
    return potential.strip()


def printed_number(text: str) -> tuple[Optional[float], Optional[int]]:
    """Central value and how many digits follow the decimal point.

    ``-32.034(4)`` yields ``(-32.034, 3)``. The parenthesis is the paper's
    uncertainty, not an extra decimal place.
    """
    cleaned = str(text or "").replace("−", "-").replace("–", "-")
    match = _NUMBER.search(cleaned)
    if match is None:
        return None, None
    decimals = len(match.group(1)) if match.group(1) else 0
    try:
        return float(match.group(0)), decimals
    except ValueError:
        return None, None


def direct_disagrees(cell_text: str, cell_value: Optional[float], median: float) -> bool:
    """True when the stored median would not round to the printed digits."""
    parsed, decimals = printed_number(cell_text)
    value = cell_value if cell_value is not None else parsed
    if value is None or decimals is None:
        return False
    tolerance = 0.5 * (10 ** (-decimals))
    return abs(float(median) - float(value)) > tolerance + 1e-15


def format_like_printed(median: float, cell_text: str) -> str:
    """Show a stored median with as many decimals as the paper printed."""
    _parsed, decimals = printed_number(cell_text)
    if decimals is None:
        return str(median)
    return f"{median:.{decimals}f}"
