"""
Parse the value of a ``solar`` schedule into a :py:class:`celery.schedules.solar`.

The value is a mapping of the event and the observer's position:
``solar: {event: sunset, lat: 48.21, lon: 16.37}`` in YAML,
``solar = { event = "sunset", lat = 48.21, lon = 16.37 }`` in TOML.

Celery computes the event times with `ephem <https://pypi.org/project/ephem/>`_,
which is only installed with the ``solar`` extra
(``pip install "action0-celery-sched[solar]"``).
"""

from enum import StrEnum
from typing import Any

from celery.schedules import solar

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import located
from action0.celery_sched.values import as_number
from action0.celery_sched.values import check_keys
from action0.celery_sched.values import expect_mapping


class SolarEvent(StrEnum):
    """
    The events a solar schedule can fire on, as Celery names them.

    >>> SolarEvent("sunset") is SolarEvent.SUNSET
    True
    """

    DAWN_ASTRONOMICAL = "dawn_astronomical"
    DAWN_NAUTICAL = "dawn_nautical"
    DAWN_CIVIL = "dawn_civil"
    SUNRISE = "sunrise"
    SOLAR_NOON = "solar_noon"
    SUNSET = "sunset"
    DUSK_CIVIL = "dusk_civil"
    DUSK_NAUTICAL = "dusk_nautical"
    DUSK_ASTRONOMICAL = "dusk_astronomical"


_KEYS = ("event", "lat", "lon")


def parse_solar(value: object) -> solar:
    """
    Turn the value of a ``solar`` key into a Celery solar schedule.

    >>> parse_solar({"event": "sunset", "lat": 48.21, "lon": 16.37})
    <solar: sunset at latitude 48.21, longitude: 16.37>

    :param value: the parsed value, from either format
    :returns: the solar schedule
    :raises DefinitionError: if the value is malformed or out of range
    :raises ImportError: if ephem (the ``solar`` extra) is not installed
    """
    mapping = expect_mapping(value)
    check_keys(mapping, allowed=_KEYS, required=_KEYS)
    with located("event"):
        event = _parse_event(mapping["event"])
    with located("lat"):
        lat = _parse_degrees(mapping["lat"], limit=90)
    with located("lon"):
        lon = _parse_degrees(mapping["lon"], limit=180)
    return _build(event, lat, lon)


def _parse_event(value: Any) -> SolarEvent:
    """Check that the event is one Celery knows."""
    try:
        return SolarEvent(value)
    except ValueError:
        choices = ", ".join(event.value for event in SolarEvent)
        raise DefinitionError(f"unknown event {value!r} (choose from: {choices})") from None


def _parse_degrees(value: Any, *, limit: int) -> int | float:
    """Check that a coordinate is a number within ``-limit..limit``."""
    degrees = as_number(value)
    if not -limit <= degrees <= limit:
        raise DefinitionError(f"must be between {-limit} and {limit}, got {degrees!r}")
    return degrees


def _build(event: SolarEvent, lat: int | float, lon: int | float) -> solar:
    """Construct the schedule, explaining a missing ephem."""
    try:
        return solar(event.value, lat, lon)
    except ImportError as error:
        raise ImportError(
            "solar schedules need ephem: pip install 'action0-celery-sched[solar]'"
        ) from error
