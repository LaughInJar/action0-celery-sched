"""
Parse the ``schedule:`` block of an entry.

The block is a mapping with exactly one key naming the kind of schedule:

.. code-block:: yaml

    schedule:
      every: 5m                     # an interval, see durations
    schedule:
      every: 1h
      relative: true                # round to the interval, see below
    schedule:
      crontab: "0 3 * * *"          # see crontabs
    schedule:
      solar: {event: sunset, lat: 48.21, lon: 16.37}   # see solar

``relative`` is Celery's own flag for intervals: when true, the time of the
next run is rounded to the resolution of the interval (a ``1h`` interval runs
on the hour). It is only allowed next to ``every``.
"""

from collections.abc import Callable
from typing import Any

from celery.schedules import BaseSchedule
from celery.schedules import schedule

from action0.celery_sched.crontabs import parse_crontab
from action0.celery_sched.durations import parse_duration
from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import located
from action0.celery_sched.solar import parse_solar
from action0.celery_sched.values import as_bool
from action0.celery_sched.values import check_keys
from action0.celery_sched.values import expect_mapping

#: the keys naming a kind of schedule; exactly one of them must be given
KINDS = ("every", "crontab", "solar")


def parse_schedule(value: object) -> BaseSchedule:
    """
    Turn the ``schedule:`` block of an entry into a Celery schedule.

    Intervals become a :py:class:`celery.schedules.schedule`, so every kind
    comes back as a :py:class:`~celery.schedules.BaseSchedule` that beat
    accepts as it is.

    >>> parse_schedule({"every": "5m"})
    <freq: 5.00 minutes>
    >>> parse_schedule({"crontab": "0 3 * * *"})
    <crontab: 0 3 * * * (m/h/dM/MY/d)>

    :param value: the parsed YAML value
    :returns: the schedule
    :raises DefinitionError: if the block is malformed
    """
    mapping = expect_mapping(value)
    check_keys(mapping, allowed=(*KINDS, "relative"))
    kind = _kind_of(mapping)
    if kind == "every":
        return _parse_every(mapping)
    if "relative" in mapping:
        raise DefinitionError("'relative' only applies to 'every' schedules")
    with located(kind):
        return _PARSERS[kind](mapping[kind])


def _kind_of(mapping: dict[str, Any]) -> str:
    """Find the one key naming the kind of schedule."""
    kinds = [kind for kind in KINDS if kind in mapping]
    if len(kinds) != 1:
        found = f"got {', '.join(kinds)}" if kinds else "got none"
        raise DefinitionError(f"expected exactly one of {', '.join(KINDS)}, {found}")
    return kinds[0]


def _parse_every(mapping: dict[str, Any]) -> schedule:
    """Build an interval schedule from ``every`` and the optional ``relative``."""
    with located("every"):
        interval = parse_duration(mapping["every"])
    with located("relative"):
        relative = as_bool(mapping.get("relative", False))
    return schedule(interval, relative=relative)


# the parsers of the kinds that take nothing but their own value
_PARSERS: dict[str, Callable[[object], BaseSchedule]] = {
    "crontab": parse_crontab,
    "solar": parse_solar,
}
