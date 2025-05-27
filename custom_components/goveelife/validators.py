"""Common validators for Govee Life integration."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def validate_numeric_value(
    value: Any, value_name: str = "value", log_prefix: str = ""
) -> float | None:
    """Validate and convert a value to float.

    Returns None if value is None, empty string, or cannot be converted.
    """
    if value in (None, ""):
        _LOGGER.debug(f"{log_prefix}{value_name} is None or empty string")
        return None

    try:
        return float(value)
    except (ValueError, TypeError) as e:
        _LOGGER.error(
            f"{log_prefix}Cannot convert {value_name} {value!r} to float: {e}"
        )
        return None


def validate_int_value(
    value: Any, value_name: str = "value", log_prefix: str = ""
) -> int | None:
    """Validate and convert a value to int.

    Returns None if value is None, empty string, or cannot be converted.
    """
    numeric = validate_numeric_value(value, value_name, log_prefix)
    return int(numeric) if numeric is not None else None


def validate_in_range(
    value: T,
    min_value: T,
    max_value: T,
    value_name: str = "value",
    log_prefix: str = "",
) -> T | None:
    """Validate that a value is within a range.

    Returns the value if in range, None otherwise.
    """
    if value is None:
        return None

    if min_value <= value <= max_value:
        return value

    _LOGGER.debug(
        f"{log_prefix}{value_name} {value} outside range [{min_value}, {max_value}]"
    )
    return None


def safe_get_dict_value(
    data: dict[str, Any], key: str, default: Any = None, log_prefix: str = ""
) -> Any:
    """Safely get a value from a dictionary with logging."""
    if not isinstance(data, dict):
        _LOGGER.debug(f"{log_prefix}Expected dict but got {type(data).__name__}")
        return default

    return data.get(key, default)
