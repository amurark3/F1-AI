"""Value coercion helpers for Ergast/FastF1 dataframes."""

from __future__ import annotations

import math
from datetime import timezone
from typing import Any


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return int(value)


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return float(value)


def safe_str(row: Any, key: str, default: str = "") -> str:
    value = row.get(key, default)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return str(value)


def utc_isoformat(value: Any) -> str:
    """Serialize FastF1 UTC timestamps with an explicit UTC designator."""

    dt = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")
