"""
A small reader for ``my_publications.bib``.

Only the fields the paper site displays are kept. Nested braces are handled so
a multiline abstract or SWHID does not swallow the next entry. There is no
BibTeX dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class Citation:
    """Bibliographic fields taken from one bib entry."""

    key: str
    title: str = ""
    authors: str = ""
    year: str = ""
    month: str = ""
    journal: str = ""
    doi: str = ""
    volume: str = ""
    pages: str = ""


def parse_bib(text: str) -> Dict[str, Citation]:
    """Parse ``@type{key, ...}`` entries into citations keyed by the cite key."""
    entries: Dict[str, Citation] = {}
    length = len(text)
    index = 0
    while index < length:
        if text[index] == "%":
            newline = text.find("\n", index)
            index = length if newline < 0 else newline + 1
            continue
        if text[index] != "@":
            index += 1
            continue
        cursor = index + 1
        while cursor < length and text[cursor].isalpha():
            cursor += 1
        if cursor >= length or text[cursor] != "{":
            index = max(cursor, index + 1)
            continue
        cursor += 1
        key_start = cursor
        while cursor < length and text[cursor] not in ",}":
            cursor += 1
        key = text[key_start:cursor].strip()
        if cursor < length and text[cursor] == ",":
            cursor += 1
        fields: Dict[str, str] = {}
        while cursor < length:
            while cursor < length and text[cursor] in " \t\r\n,":
                cursor += 1
            if cursor >= length:
                break
            if text[cursor] == "}":
                cursor += 1
                break
            if text[cursor] == "%":
                newline = text.find("\n", cursor)
                cursor = length if newline < 0 else newline + 1
                continue
            name_start = cursor
            while cursor < length and (text[cursor].isalnum() or text[cursor] in "_-"):
                cursor += 1
            name = text[name_start:cursor].strip().lower()
            while cursor < length and text[cursor] in " \t\r\n":
                cursor += 1
            if cursor >= length or text[cursor] != "=":
                cursor += 1
                continue
            cursor += 1
            while cursor < length and text[cursor] in " \t\r\n":
                cursor += 1
            if cursor >= length:
                break
            if text[cursor] == "{":
                value, cursor = _read_braced(text, cursor)
            elif text[cursor] == '"':
                value, cursor = _read_quoted(text, cursor)
            else:
                value_start = cursor
                while cursor < length and text[cursor] not in ",}\n":
                    cursor += 1
                value = text[value_start:cursor].strip()
            if name:
                fields[name] = value.strip()
        if key:
            entries[key] = _citation(key, fields)
        index = cursor
    return entries


def load_bibliography(path: Path) -> Dict[str, Citation]:
    """Read a bib file. OS and decode errors propagate to the caller."""
    return parse_bib(Path(path).read_text(encoding="utf-8"))


def published_label(year: str, month: str = "") -> str:
    """``Jun 2024`` when a month is known, otherwise the year alone."""
    year_text = re.sub(r"\D", "", str(year or "")) or str(year or "").strip()
    month_name = _MONTHS.get(_month_key(month))
    if month_name and year_text:
        return f"{month_name} {year_text}"
    return year_text or str(year or "").strip()


def published_sort(year: str, month: str = "") -> str:
    """``YYYY-MM`` so the papers table can sort by date."""
    year_text = re.sub(r"\D", "", str(year or ""))
    month_number = _MONTH_NUMBERS.get(_month_key(month), 0)
    if not year_text:
        return ""
    return f"{year_text}-{month_number:02d}"


_MONTHS = {
    "1": "Jan", "01": "Jan", "jan": "Jan", "january": "Jan",
    "2": "Feb", "02": "Feb", "feb": "Feb", "february": "Feb",
    "3": "Mar", "03": "Mar", "mar": "Mar", "march": "Mar",
    "4": "Apr", "04": "Apr", "apr": "Apr", "april": "Apr",
    "5": "May", "05": "May", "may": "May",
    "6": "Jun", "06": "Jun", "jun": "Jun", "june": "Jun",
    "7": "Jul", "07": "Jul", "jul": "Jul", "july": "Jul",
    "8": "Aug", "08": "Aug", "aug": "Aug", "august": "Aug",
    "9": "Sep", "09": "Sep", "sep": "Sep", "sept": "Sep", "september": "Sep",
    "10": "Oct", "oct": "Oct", "october": "Oct",
    "11": "Nov", "nov": "Nov", "november": "Nov",
    "12": "Dec", "dec": "Dec", "december": "Dec",
}
_MONTH_NUMBERS = {key: index for index, name in enumerate(
    ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
) for key, month_name in _MONTHS.items() if month_name == name}


def _month_key(month: str) -> str:
    return re.sub(r"[{}\s]", "", str(month or "")).casefold()


def normalize_doi(value: str) -> str:
    """Strip a resolver prefix and compare DOIs case-insensitively."""
    text = str(value or "").strip()
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix):]
            break
    return text.strip().lower()


def normalize_text(value: str) -> str:
    """Drop TeX braces and collapse whitespace for a title or year comparison."""
    text = re.sub(r"[{}]", "", str(value or ""))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _citation(key: str, fields: Dict[str, str]) -> Citation:
    journal = fields.get("fjournal") or fields.get("journal") or ""
    return Citation(
        key=key,
        title=fields.get("title") or "",
        authors=fields.get("author") or "",
        year=fields.get("year") or "",
        month=fields.get("month") or "",
        journal=journal,
        doi=fields.get("doi") or "",
        volume=fields.get("volume") or "",
        pages=fields.get("pages") or "",
    )


def _read_braced(text: str, index: int) -> tuple[str, int]:
    """Read a ``{...}`` value. ``index`` points at the opening brace."""
    depth = 0
    start = index
    length = len(text)
    while index < length:
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
        index += 1
    return text[start + 1:], length


def _read_quoted(text: str, index: int) -> tuple[str, int]:
    """Read a double-quoted value. ``index`` points at the opening quote."""
    index += 1
    start = index
    length = len(text)
    while index < length:
        if text[index] == '"' and text[index - 1] != "\\":
            return text[start:index], index + 1
        index += 1
    return text[start:], length
