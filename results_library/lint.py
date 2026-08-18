"""
Consistency checks over the whole library.

These run across bundles, which is the only place some problems are visible: a
duplicate id, an artifact that was pruned away, or the same state recorded with
two different isospins. None of them are fatal -- the catalog still builds -- but
each one silently degrades trust in the numbers, so they are reported.

Note the deliberate asymmetry with the pipeline's early config check: that one
validates a single declaration before a run, this one validates the accumulated
library afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from results_library import SUPPORTED_SCHEMA_VERSION
from results_library.annotations import lint_annotations, load_annotations
from results_library.catalog import ScanResult

#: Ordered by how much they should worry you.
SEVERITIES = ("error", "warning", "info")


@dataclass(frozen=True)
class LintIssue:
    severity: str
    kind: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.kind}: {self.message}"


def _check_unreadable(scan: ScanResult) -> List[LintIssue]:
    return [
        LintIssue("error", "unreadable", message)
        for message in scan.unreadable
    ]


def _check_duplicate_ids(scan: ScanResult) -> List[LintIssue]:
    """Two bundles claiming one id means one of them is unreachable."""
    seen: Dict[str, List[Path]] = {}
    for record in scan.records:
        seen.setdefault(record.result_id, []).append(record.path)

    issues: List[LintIssue] = []
    for result_id, paths in seen.items():
        if len(paths) > 1:
            locations = ", ".join(str(p) for p in paths)
            issues.append(
                LintIssue(
                    "error",
                    "duplicate-id",
                    f"{result_id or '<missing id>'} appears in {len(paths)} "
                    f"bundles: {locations}",
                )
            )
    return issues


def _check_id_matches_location(scan: ScanResult) -> List[LintIssue]:
    """The bundle path mirrors the id; a mismatch means one was hand-edited."""
    issues: List[LintIssue] = []
    for record in scan.records:
        if not record.result_id:
            issues.append(
                LintIssue("error", "missing-id", f"{record.path} has no 'id' field")
            )
            continue

        expected_tail = record.result_id.replace("/", "\\") if "\\" in str(
            record.bundle_dir
        ) else record.result_id
        if not str(record.bundle_dir).replace("\\", "/").endswith(
            record.result_id.replace("\\", "/")
        ):
            issues.append(
                LintIssue(
                    "warning",
                    "path-mismatch",
                    f"{record.result_id} is stored at {record.bundle_dir}, which "
                    f"does not end with the id (expected .../{expected_tail})",
                )
            )
    return issues


def _check_family(scan: ScanResult) -> List[LintIssue]:
    from results_schema.slugs import family_of

    issues: List[LintIssue] = []
    for record in scan.records:
        if not record.result_id:
            continue
        try:
            expected = family_of(record.result_id)
        except ValueError as exc:
            issues.append(
                LintIssue("error", "bad-id", f"{record.result_id}: {exc}")
            )
            continue
        actual = record.data.get("family")
        if actual != expected:
            issues.append(
                LintIssue(
                    "error",
                    "family-mismatch",
                    f"{record.result_id} has family {actual!r}, expected "
                    f"{expected!r}; grouping and comparison will be wrong",
                )
            )
    return issues


def _check_artifacts(scan: ScanResult) -> List[LintIssue]:
    """A declared artifact that is gone makes a download link dead."""
    issues: List[LintIssue] = []
    for record in scan.records:
        artifacts: Dict[str, str] = record.data.get("artifacts") or {}
        for key, filename in artifacts.items():
            if not (record.bundle_dir / filename).exists():
                issues.append(
                    LintIssue(
                        "warning",
                        "missing-artifact",
                        f"{record.result_id}: {key} points at {filename}, which "
                        f"is not in the bundle",
                    )
                )

        available = record.data.get("available") or []
        for stem in available:
            if not any(key.startswith(f"{stem}_") for key in artifacts):
                issues.append(
                    LintIssue(
                        "info",
                        "unbacked-availability",
                        f"{record.result_id}: '{stem}' is listed as available but "
                        f"has no artifact entry",
                    )
                )
    return issues


def _check_conflicting_isospin(scan: ScanResult) -> List[LintIssue]:
    """Same state, two isospins.

    ``(J, pi, n)`` already identifies a state, so isospin is redundant
    information carried for readability. That redundancy is useful precisely
    here: if one state has been recorded with two different ``T`` values, at
    least one declaration is wrong.
    """
    seen: Dict[tuple, Dict[int, List[str]]] = {}

    def visit(nucleus: Any, state: Any, result_id: str) -> None:
        if not isinstance(state, dict) or nucleus is None:
            return
        key = (str(nucleus), state.get("J2"), state.get("parity"), state.get("index"))
        isospin = state.get("T2")
        if isospin is None:
            return
        seen.setdefault(key, {}).setdefault(int(isospin), []).append(result_id)

    for record in scan.records:
        subject = record.data.get("subject") or {}
        if subject.get("kind") == "transition":
            for side in ("initial", "final"):
                endpoint = subject.get(side) or {}
                visit(endpoint.get("nucleus"), endpoint.get("state"), record.result_id)
        else:
            visit(subject.get("nucleus"), subject.get("state"), record.result_id)

    issues: List[LintIssue] = []
    for (nucleus, j2, parity, index), by_isospin in seen.items():
        if len(by_isospin) > 1:
            detail = "; ".join(
                f"T2={t2} in {len(ids)} result(s)" for t2, ids in sorted(by_isospin.items())
            )
            issues.append(
                LintIssue(
                    "error",
                    "conflicting-isospin",
                    f"{nucleus} state J2={j2} parity={parity} index={index} is "
                    f"recorded with more than one isospin: {detail}. At least one "
                    f"identity declaration is wrong.",
                )
            )
    return issues


def _check_schema_version(scan: ScanResult) -> List[LintIssue]:
    issues: List[LintIssue] = []
    for record in scan.records:
        version = int(record.data.get("schema_version", 1))
        if version > SUPPORTED_SCHEMA_VERSION:
            issues.append(
                LintIssue(
                    "warning",
                    "future-schema",
                    f"{record.result_id} has schema_version {version}, newer than "
                    f"the supported {SUPPORTED_SCHEMA_VERSION}; fields may be "
                    f"missing from the catalog. Update this tooling.",
                )
            )
    return issues


def _check_model_validity(scan: ScanResult) -> List[LintIssue]:
    """Strict validation, when pydantic is available.

    Optional on purpose: the catalog must still build in a bare environment.
    """
    try:
        from results_schema.models import ResultRecord
    except ImportError:
        return [
            LintIssue(
                "info",
                "validation-skipped",
                "pydantic is not installed, so records were not strictly validated",
            )
        ]

    issues: List[LintIssue] = []
    for record in scan.records:
        try:
            ResultRecord.model_validate(record.data)
        except Exception as exc:
            issues.append(
                LintIssue(
                    "error",
                    "invalid-record",
                    f"{record.result_id or record.path}: {exc}",
                )
            )
    return issues


def lint_library(library_root: Path, scan: ScanResult) -> List[LintIssue]:
    """Run every check and return the issues found, worst first."""
    issues: List[LintIssue] = []
    issues.extend(_check_unreadable(scan))
    issues.extend(_check_duplicate_ids(scan))
    issues.extend(_check_id_matches_location(scan))
    issues.extend(_check_family(scan))
    issues.extend(_check_artifacts(scan))
    issues.extend(_check_conflicting_isospin(scan))
    issues.extend(_check_schema_version(scan))
    issues.extend(_check_model_validity(scan))

    known_ids = {record.result_id for record in scan.records}
    issues.extend(
        LintIssue("warning", "annotation", message)
        for message in lint_annotations(load_annotations(library_root), known_ids)
    )

    order = {severity: rank for rank, severity in enumerate(SEVERITIES)}
    return sorted(issues, key=lambda issue: (order.get(issue.severity, 9), issue.kind))


def summarise(issues: List[LintIssue]) -> Dict[str, int]:
    counts = {severity: 0 for severity in SEVERITIES}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    return counts
