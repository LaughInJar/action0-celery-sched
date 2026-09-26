"""
Parse the interval of an ``every`` schedule.

Three spellings are accepted:

- a number of seconds: ``30``, ``2.5`` (or the same as a string, which is what
  ``!ENV`` produces);
- a duration string of ``<amount><unit>`` parts: ``90s``, ``5m``,
  ``1h30m``, ``1.5h``, ``2d 12h`` — units ``w``, ``d``, ``h``, ``m``, ``s``
  and ``ms``, lowercase only (so ``m`` can never be misread as months);
- a mapping of :py:class:`~datetime.timedelta` arguments:
  ``{hours: 1, minutes: 30}`` in YAML, ``{ hours = 1, minutes = 30 }`` in TOML.
"""

import math
import re
from datetime import timedelta
from typing import Any

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import located
from action0.celery_sched.values import as_number
from action0.celery_sched.values import check_keys
from action0.celery_sched.values import describe

# seconds per unit of a duration string
_UNIT_SECONDS: dict[str, float] = {
    "w": 7 * 24 * 3600,
    "d": 24 * 3600,
    "h": 3600,
    "m": 60,
    "s": 1,
    "ms": 0.001,
}

# the keyword arguments of timedelta that make sense for a schedule
_MAPPING_KEYS = ("weeks", "days", "hours", "minutes", "seconds", "milliseconds")

# one "<amount><unit>" part; "ms" is listed before "m" so it wins the alternation
_PART = r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>ms|[wdhms])"
_PART_PATTERN = re.compile(_PART)
_DURATION_PATTERN = re.compile(rf"\s*(?:{_PART}\s*)+")


def parse_duration(value: object) -> timedelta:
    """
    Turn the value of an ``every`` key into a positive :py:class:`~datetime.timedelta`.

    >>> parse_duration(90)
    datetime.timedelta(seconds=90)
    >>> parse_duration("1h30m")
    datetime.timedelta(seconds=5400)
    >>> parse_duration({"days": 1, "hours": 12})
    datetime.timedelta(days=1, seconds=43200)

    :param value: the parsed value, from either format
    :returns: the interval
    :raises DefinitionError: if the value is malformed, zero or negative
    """
    if isinstance(value, dict):
        interval = _from_mapping(value)
    elif isinstance(value, str) and not _looks_numeric(value):
        interval = _from_string(value)
    else:
        interval = _from_seconds(as_number(value))
    if interval <= timedelta(0):
        raise DefinitionError(f"the interval must be positive, got {describe(value)}")
    return interval


def _looks_numeric(text: str) -> bool:
    """Tell a bare number (seconds) from a duration string."""
    try:
        as_number(text)
    except DefinitionError:
        return False
    return True


def _from_seconds(seconds: int | float) -> timedelta:
    """Build the interval from a plain number of seconds."""
    if not math.isfinite(seconds):
        raise DefinitionError(f"the interval must be finite, got {seconds!r}")
    try:
        return timedelta(seconds=seconds)
    except OverflowError:
        raise DefinitionError(f"the interval is too large: {seconds!r} seconds") from None


def _from_string(text: str) -> timedelta:
    """Build the interval from a duration string like ``1h30m``."""
    if not _DURATION_PATTERN.fullmatch(text):
        raise DefinitionError(
            f"expected seconds or a duration like '90s', '5m' or '1h30m', got {text!r}"
        )
    seconds = sum(
        float(match["amount"]) * _UNIT_SECONDS[match["unit"]]
        for match in _PART_PATTERN.finditer(text)
    )
    return _from_seconds(seconds)


def _from_mapping(mapping: dict[str, Any]) -> timedelta:
    """Build the interval from ``timedelta`` keyword arguments."""
    check_keys(mapping, allowed=_MAPPING_KEYS)
    if not mapping:
        raise DefinitionError(f"expected at least one of: {', '.join(_MAPPING_KEYS)}")
    arguments: dict[str, float] = {}
    for key, amount in mapping.items():
        with located(key):
            arguments[key] = as_number(amount)
            if not math.isfinite(arguments[key]):
                raise DefinitionError(f"must be finite, got {amount!r}")
    try:
        return timedelta(**arguments)
    except OverflowError:
        raise DefinitionError("the interval is too large") from None
