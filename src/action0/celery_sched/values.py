"""
Small validators shared by the parsers.

They all raise :py:class:`~action0.celery_sched.errors.DefinitionError`
with a reason only; the callers add the location. Scalars may arrive as
strings where YAML would normally give a number or a boolean — that is what
``!ENV`` substitution produces — so the number and boolean validators accept
the string spellings too.
"""

from collections.abc import Collection
from typing import Any

from action0.celery_sched.errors import DefinitionError

# the spellings accepted for booleans given as strings (YAML 1.1's, minus y/n)
_TRUE = frozenset({"true", "yes", "on", "1"})
_FALSE = frozenset({"false", "no", "off", "0"})


def describe(value: object) -> str:
    """
    Render a value for an error message: its type and a short repr.

    >>> describe("five")
    "str 'five'"
    >>> describe(None)
    'null'

    :param value: the offending value
    :returns: a short description
    """
    if value is None:
        return "null"
    text = repr(value)
    if len(text) > 40:
        text = text[:37] + "..."
    return f"{type(value).__name__} {text}"


def expect_mapping(value: object) -> dict[str, Any]:
    """
    Check that a value is a mapping with string keys.

    >>> expect_mapping({"task": "myapp.tasks.poll"})
    {'task': 'myapp.tasks.poll'}

    :param value: the parsed YAML value
    :returns: the value, typed as a dict
    :raises DefinitionError: if it isn't a mapping, or a key isn't a string
    """
    if not isinstance(value, dict):
        raise DefinitionError(f"expected a mapping, got {describe(value)}")
    for key in value:
        if not isinstance(key, str):
            raise DefinitionError(f"keys must be strings, got {describe(key)}")
    return value


def check_keys(
    mapping: dict[str, Any], *, allowed: Collection[str], required: Collection[str] = ()
) -> None:
    """
    Reject unknown keys (typos, mostly) and report missing required ones.

    >>> check_keys({"task": "x", "shedule": {}}, allowed=["task", "schedule"])
    Traceback (most recent call last):
    ...
    action0.celery_sched.errors.DefinitionError: unknown key 'shedule' (allowed: schedule, task)

    :param mapping: the mapping to check
    :param allowed: every key that may appear
    :param required: the keys that must appear
    :raises DefinitionError: on the first unknown or missing key
    """
    for key in mapping:
        if key not in allowed:
            raise DefinitionError(f"unknown key {key!r} (allowed: {', '.join(sorted(allowed))})")
    for key in required:
        if key not in mapping:
            raise DefinitionError(f"missing required key {key!r}")


def as_number(value: object) -> int | float:
    """
    Check that a value is a number, or a string holding one.

    >>> as_number(1.5), as_number("30")
    (1.5, 30)

    :param value: the parsed YAML value
    :returns: the number, an ``int`` where the input was integral text
    :raises DefinitionError: if the value is not a number (booleans aren't)
    """
    if isinstance(value, bool):
        raise DefinitionError(f"expected a number, got {describe(value)}")
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            pass
    raise DefinitionError(f"expected a number, got {describe(value)}")


def as_bool(value: object) -> bool:
    """
    Check that a value is a boolean, or a string spelling one.

    >>> as_bool(False), as_bool("yes"), as_bool("OFF")
    (False, True, False)

    :param value: the parsed YAML value
    :returns: the boolean
    :raises DefinitionError: if the value is neither
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    raise DefinitionError(f"expected a boolean, got {describe(value)}")
