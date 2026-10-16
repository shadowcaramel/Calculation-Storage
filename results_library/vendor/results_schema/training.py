"""
Training setup stored next to a result: the learning rate and its schedule.

``result.json`` keeps this in a top-level ``training`` block, not on
``variant``, so it never changes hashes. Two runs that differ only in schedule
share ``variant_hash`` and are told apart by this block.

Stdlib only, so the library catalog can derive the block from an older
bundle's ``config_snapshot.toml`` without pydantic installed.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

#: Config keys each schedule type reads in the pipeline's ``src/optimizers.py``.
LR_SCHEDULE_PARAMETERS: Dict[str, tuple] = {
    "constant": (),
    "cosine_decay": ("decay_steps", "alpha"),
    "cosine_decay_warmup": ("decay_steps", "warmup_steps", "alpha"),
    "cosine_decay_restarts": ("first_decay_steps", "t_mul", "m_mul", "alpha"),
    "peak_envelope": ("first_decay_steps", "m_mul"),
}

_LR_SCHEDULE_NAMES = {
    "constant": "constant",
    "cosine_decay": "cosine decay",
    "cosine_decay_warmup": "cosine decay with warm-up",
    "cosine_decay_restarts": "cosine restarts",
    "peak_envelope": "peak envelope",
}


def _config_number(value: Any) -> Optional[float]:
    """Numeric config value, or ``None`` for missing, ``"None"`` and non-numbers."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if text.lower() in ("", "none", "null"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def training_from_config(config: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """``training`` block from ``[training]`` and ``[training.lr_schedule]``.

    Follows the trainer: the schedule applies only when ``enabled`` is true
    and ``type`` is not ``"none"``; otherwise the rate is ``constant``.
    Parameters left to the pipeline default (missing or ``"None"``) are
    omitted. Returns ``None`` when the config has no learning rate.
    """
    training = config.get("training")
    if not isinstance(training, Mapping):
        return None
    rate = _config_number(training.get("learning_rate"))
    if rate is None:
        return None
    schedule_cfg = training.get("lr_schedule")
    if not isinstance(schedule_cfg, Mapping):
        schedule_cfg = {}
    kind = str(schedule_cfg.get("type") or "none").strip().lower()
    if not schedule_cfg.get("enabled", False) or kind == "none":
        kind = "constant"
    schedule: Dict[str, Any] = {"type": kind}
    for key in LR_SCHEDULE_PARAMETERS.get(kind, ()):
        value = _config_number(schedule_cfg.get(key))
        if value is not None:
            schedule[key] = value
    return {"learning_rate": float(rate), "lr_schedule": schedule}


def _format_setting(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def lr_schedule_label(
    training: Optional[Mapping[str, Any]], detailed: bool = False
) -> Optional[str]:
    """``cosine restarts, η₀ = 0.005`` from a record's ``training`` block.

    A constant rate reads ``constant, η = 0.0001``. ``detailed`` appends the
    schedule parameters as written in the config, e.g.
    ``(first_decay_steps = 40000, m_mul = 0.85)``. ``None`` when the block is
    absent.
    """
    if not training:
        return None
    schedule = training.get("lr_schedule") or {}
    kind = str(schedule.get("type") or "constant")
    parts = [_LR_SCHEDULE_NAMES.get(kind, kind)]
    rate = training.get("learning_rate")
    if rate is not None:
        symbol = "η" if kind == "constant" else "η₀"
        parts.append(f"{symbol} = {_format_setting(float(rate))}")
    label = ", ".join(parts)
    if detailed:
        settings = [
            f"{key} = {_format_setting(value)}"
            for key, value in schedule.items()
            if key != "type"
        ]
        if settings:
            label += f" ({', '.join(settings)})"
    return label
