"""
One schedule entry: the YAML shape, its parsed form and Celery's.

In YAML an entry is a named mapping:

.. code-block:: yaml

    "Nightly report":                     # the entry's name, unique
      task: myapp.reports.tasks.nightly   # the registered task name — required
      schedule:                           # when to run it — required
        crontab: "0 3 * * *"
      params: [daily]                     # positional arguments
      kw:                                 # keyword arguments
        recipients: [ops@example.com]
      options:                            # passed on to apply_async()
        queue: reports
      enabled: true                       # false keeps the entry but skips it

Any other key is an error, so a typo like ``shedule:`` fails at startup
instead of silently dropping the schedule.
"""

import copy
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import TypedDict

from celery.schedules import BaseSchedule

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import located
from action0.celery_sched.schedules import parse_schedule
from action0.celery_sched.values import as_bool
from action0.celery_sched.values import check_keys
from action0.celery_sched.values import describe
from action0.celery_sched.values import expect_mapping

#: every key an entry may have
ENTRY_KEYS = ("task", "schedule", "params", "kw", "options", "enabled")

_REQUIRED_KEYS = ("task", "schedule")


class BeatEntry(TypedDict):
    """
    One value of Celery's ``beat_schedule`` setting, as beat expects it.
    """

    task: str
    schedule: BaseSchedule
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    options: dict[str, Any]


@dataclass(frozen=True)
class Entry:
    """
    A parsed and validated schedule entry.

    >>> entry = parse_entry("Poll feed", {"task": "myapp.tasks.poll", "schedule": {"every": 30}})
    >>> entry.to_celery()
    {'task': 'myapp.tasks.poll', 'schedule': <freq: 30.00 seconds>, 'args': (), 'kwargs': {}, 'options': {}}
    """

    #: the entry's name — the key in ``beat_schedule``
    name: str
    #: the name the task is registered under
    task: str
    #: when the task runs
    schedule: BaseSchedule
    #: positional arguments (``params:`` in YAML)
    args: tuple[Any, ...] = ()
    #: keyword arguments (``kw:`` in YAML)
    kwargs: dict[str, Any] = field(default_factory=dict)
    #: ``apply_async()`` options such as ``queue``, ``priority`` or ``expires``
    options: dict[str, Any] = field(default_factory=dict)
    #: whether the entry goes into the beat schedule at all
    enabled: bool = True
    #: the file (or stream name) the entry was read from, if known
    source: str | None = field(default=None, compare=False)

    def to_celery(self) -> BeatEntry:
        """
        Render the entry as a ``beat_schedule`` value.

        :returns: a fresh dict; mutating it does not affect the entry
        """
        return {
            "task": self.task,
            "schedule": self.schedule,
            "args": self.args,
            "kwargs": copy.deepcopy(self.kwargs),
            "options": copy.deepcopy(self.options),
        }


def parse_entry(name: str, value: object, *, source: str | None = None) -> Entry:
    """
    Validate one entry of a schedule file.

    The argument containers are deep-copied, so entries sharing a mapping
    through a YAML anchor never share it at runtime.

    :param name: the entry's name (its key in the file)
    :param value: the parsed YAML value of the entry
    :param source: where the entry was read from, recorded on the entry
    :returns: the entry
    :raises DefinitionError: if the entry is malformed
    """
    with located(entry=name, source=source):
        mapping = expect_mapping(value)
        check_keys(mapping, allowed=ENTRY_KEYS, required=_REQUIRED_KEYS)
        with located("task"):
            task = _parse_task(mapping["task"])
        with located("schedule"):
            schedule = parse_schedule(mapping["schedule"])
        with located("params"):
            args = _parse_args(mapping.get("params"))
        with located("kw"):
            kwargs = _parse_mapping(mapping.get("kw"))
        with located("options"):
            options = _parse_mapping(mapping.get("options"))
        with located("enabled"):
            enabled = as_bool(mapping.get("enabled", True))
    return Entry(name, task, schedule, args, kwargs, options, enabled, source)


def _parse_task(value: object) -> str:
    """Check the task name: a non-blank string."""
    if not isinstance(value, str) or not value.strip():
        raise DefinitionError(f"expected a task name, got {describe(value)}")
    return value.strip()


def _parse_args(value: object) -> tuple[Any, ...]:
    """Check the positional arguments: a list, or nothing."""
    if value is None:  # "params:" with nothing after it
        return ()
    if not isinstance(value, list):
        raise DefinitionError(f"expected a list, got {describe(value)}")
    return tuple(copy.deepcopy(value))


def _parse_mapping(value: object) -> dict[str, Any]:
    """Check keyword arguments or options: a string-keyed mapping, or nothing."""
    if value is None:  # "kw:" with nothing after it
        return {}
    return copy.deepcopy(expect_mapping(value))
