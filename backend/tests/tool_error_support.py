"""What a tool tells the model when it fails for a reason the reader must not see."""

from __future__ import annotations

import re

from app.api.errors import ERROR_ID_LENGTH, GENERIC_ERROR_MESSAGE


def is_generic_failure(text: str, prefix: str) -> bool:
    """``text`` is the tool's own prefix, the generic line and a reference id, and nothing raw."""
    pattern = rf"{re.escape(prefix)}: {re.escape(GENERIC_ERROR_MESSAGE)} \(reference: [0-9a-f]{{{ERROR_ID_LENGTH}}}\)"
    return re.fullmatch(pattern, text) is not None
