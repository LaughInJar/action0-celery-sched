"""
Exceptions raised while reading schedules; everything derives from :py:class:`ScheduleError`.
"""

from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import contextmanager


class ScheduleError(Exception):
    """
    Base class of every error this package raises on purpose.
    """


class DefinitionError(ScheduleError):
    """
    A schedule file, or one entry in it, is malformed.

    The error knows *where* the problem is: the file it came from, the entry
    and the key path inside that entry. The parsers only state the
    :py:attr:`reason`; the location is filled in on the way up (see
    :py:func:`located`), so the message reads like::

        beat.yaml: entry 'Nightly report': schedule.crontab: expected 5 fields, got 4

    >>> error = DefinitionError("expected 5 fields, got 4")
    >>> error.source, error.entry, error.path = "beat.yaml", "Nightly report", ("schedule", "crontab")
    >>> print(error)
    beat.yaml: entry 'Nightly report': schedule.crontab: expected 5 fields, got 4
    """

    def __init__(self, reason: str) -> None:
        """
        :param reason: what is wrong, without the location
        """
        super().__init__(reason)
        self.reason = reason
        #: the file (or stream name) the entry was read from, if known
        self.source: str | None = None
        #: the name of the entry, if the error is inside one
        self.entry: str | None = None
        #: the keys leading from the entry to the offending value
        self.path: tuple[str, ...] = ()

    def __str__(self) -> str:
        parts = []
        if self.source is not None:
            parts.append(self.source)
        if self.entry is not None:
            parts.append(f"entry {self.entry!r}")
        if self.path:
            parts.append(".".join(self.path))
        parts.append(self.reason)
        return ": ".join(parts)


class DuplicateEntryError(DefinitionError):
    """
    Two entries share a name — within one file, or across files merged
    without ``replace=True``.
    """


class UnknownTaskError(ScheduleError):
    """
    Entries refer to tasks the Celery app has not registered.

    Raised by :py:func:`~action0.celery_sched.tasks.check_tasks`, listing
    *every* offender at once rather than only the first.

    >>> print(UnknownTaskError({"Nightly report": "myapp.tasks.nightly"}))
    unregistered tasks: 'Nightly report' -> myapp.tasks.nightly
    """

    def __init__(self, missing: Mapping[str, str]) -> None:
        """
        :param missing: entry name → the task name nothing is registered under
        """
        self.missing = dict(missing)
        listing = ", ".join(f"{entry!r} -> {task}" for entry, task in self.missing.items())
        super().__init__(f"unregistered tasks: {listing}")


@contextmanager
def located(*keys: str, entry: str | None = None, source: str | None = None) -> Iterator[None]:
    """
    Add location details to any :py:class:`DefinitionError` raised inside the block.

    Nest these as the parsers descend into a value, so each layer only needs
    to know its own key (or entry name, or file):

    >>> try:
    ...     with located(entry="Poll feed"):
    ...         with located("schedule"):
    ...             with located("every"):
    ...                 raise DefinitionError("must be positive")
    ... except DefinitionError as error:
    ...     print(error)
    entry 'Poll feed': schedule.every: must be positive

    :param keys: the keys this block descends into, prepended to the path
    :param entry: the entry this block parses, unless the error already has one
    :param source: the file this block reads, unless the error already has one
    """
    try:
        yield
    except DefinitionError as error:
        error.path = (*keys, *error.path)
        if error.entry is None:
            error.entry = entry
        if error.source is None:
            error.source = source
        raise
