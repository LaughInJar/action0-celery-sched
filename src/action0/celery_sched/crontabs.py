"""
Parse the value of a ``crontab`` schedule into a :py:class:`celery.schedules.crontab`.

Two spellings are accepted:

- a classic five-field cron string, ``"minute hour day-of-month month
  day-of-week"`` — for example ``"30 7 * * mon-fri"`` — or one of the
  nicknames ``@hourly``, ``@daily``/``@midnight``, ``@weekly``, ``@monthly``
  and ``@yearly``/``@annually``;
- a mapping of Celery's own keyword arguments, where omitted fields mean
  ``*``: ``{minute: 30, hour: 7, day_of_week: mon-fri}`` in YAML,
  ``{ minute = 30, hour = 7, day_of_week = "mon-fri" }`` in TOML.

Each field takes whatever Celery takes — ``*/15``, ``1-5``, ``mon,wed``, a
plain number — and in the mapping form also a list of numbers. Every field
is validated by Celery while loading, so a typo fails at startup, not when
beat first evaluates the schedule.
"""

from typing import Any
from typing import TypeAlias

from celery.schedules import crontab

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import located
from action0.celery_sched.values import check_keys
from action0.celery_sched.values import describe
from action0.celery_sched.values import expect_mapping

# the fields of a cron string, in cron (not Celery argument) order
FIELDS = ("minute", "hour", "day_of_month", "month_of_year", "day_of_week")

# the non-standard cron macros, as their five-field equivalent
NICKNAMES = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

# what a single field may be; Celery also takes sets, which YAML can't express
_Cronspec: TypeAlias = str | int | list[int]


def parse_crontab(value: object) -> crontab:
    """
    Turn the value of a ``crontab`` key into a Celery crontab.

    >>> parse_crontab("30 7 * * mon-fri")
    <crontab: 30 7 * * mon-fri (m/h/dM/MY/d)>
    >>> parse_crontab({"minute": "*/15"})
    <crontab: */15 * * * * (m/h/dM/MY/d)>
    >>> parse_crontab("@daily")
    <crontab: 0 0 * * * (m/h/dM/MY/d)>

    :param value: the parsed value, from either format
    :returns: the crontab
    :raises DefinitionError: if the value is malformed or a field is invalid
    """
    if isinstance(value, str):
        fields = _fields_from_string(value)
    else:
        fields = _fields_from_mapping(expect_mapping(value))
    for field, spec in fields.items():
        with located(field):
            _check_field(field, spec)
    return crontab(**fields)


def _fields_from_string(text: str) -> dict[str, _Cronspec]:
    """Split a cron string (or expand a nickname) into its named fields."""
    text = NICKNAMES.get(text.strip().lower(), text)
    parts = text.split()
    if len(parts) != len(FIELDS):
        raise DefinitionError(
            f"expected 5 fields (minute hour day-of-month month day-of-week) or a "
            f"nickname like '@daily', got {len(parts)} in {text!r}"
        )
    return dict(zip(FIELDS, parts, strict=True))


def _fields_from_mapping(mapping: dict[str, Any]) -> dict[str, _Cronspec]:
    """Check the named fields of the mapping form."""
    check_keys(mapping, allowed=FIELDS)
    fields: dict[str, _Cronspec] = {}
    for field, spec in mapping.items():
        with located(field):
            fields[field] = _as_cronspec(spec)
    return fields


def _as_cronspec(spec: object) -> _Cronspec:
    """Check that one field holds a type Celery can parse."""
    if isinstance(spec, list):
        if not all(isinstance(item, int) and not isinstance(item, bool) for item in spec):
            raise DefinitionError(f"a list may only hold numbers, got {describe(spec)}")
        return spec
    if isinstance(spec, str | int) and not isinstance(spec, bool):
        return spec
    raise DefinitionError(
        f"expected a string, a number or a list of numbers, got {describe(spec)}"
    )


def _check_field(field: str, spec: _Cronspec) -> None:
    """
    Let Celery validate a single field.

    Celery validates while constructing a crontab but doesn't say which field
    it choked on; building one per field pins the error to its key.
    """
    try:
        crontab(**{field: spec})
    except ValueError as error:
        raise DefinitionError(f"invalid value {spec!r}: {error}") from None
