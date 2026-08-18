"""
Schema migrations, applied on read.

Records are never rewritten in place by the catalog build: a stored bundle is
immutable, so an old record is upgraded in memory each time it is read. That
keeps the build idempotent and means a failed build can never corrupt the
library.

Adding a migration:

    @register(1)
    def _v1_to_v2(record: dict) -> dict:
        record["computed"]["uncertainty_method"] = "IQR"
        return record

Each function takes a record at version ``N`` and returns it at ``N + 1``. Keep
them idempotent and defensive: they run against real data written months
earlier, where any optional field may be missing.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)

Migration = Callable[[Dict[str, Any]], Dict[str, Any]]

#: from_version -> upgrade function
MIGRATIONS: Dict[int, Migration] = {}


def register(from_version: int) -> Callable[[Migration], Migration]:
    """Register a migration from ``from_version`` to ``from_version + 1``."""

    def decorator(func: Migration) -> Migration:
        if from_version in MIGRATIONS:
            raise ValueError(
                f"A migration from version {from_version} is already registered "
                f"({MIGRATIONS[from_version].__name__})"
            )
        MIGRATIONS[from_version] = func
        return func

    return decorator


def latest_version() -> int:
    """Version reached after applying every registered migration."""
    from results_library import SUPPORTED_SCHEMA_VERSION

    if not MIGRATIONS:
        return SUPPORTED_SCHEMA_VERSION
    return max(max(MIGRATIONS) + 1, SUPPORTED_SCHEMA_VERSION)


def apply_migrations(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Upgrade one record to the latest known version.

    Returns ``(record, applied)`` where ``applied`` names each migration used, so
    the build can report what it had to upgrade. A record from the future is left
    untouched and reported by the lint pass rather than guessed at.
    """
    applied: List[str] = []
    version = int(record.get("schema_version", 1))
    target = latest_version()

    while version < target:
        migration = MIGRATIONS.get(version)
        if migration is None:
            logger.warning(
                "No migration registered from schema_version %d; leaving record "
                "%s as-is.",
                version,
                record.get("id", "<unknown>"),
            )
            break
        record = migration(dict(record))
        version += 1
        record["schema_version"] = version
        applied.append(f"v{version - 1}->v{version}")

    return record, applied
