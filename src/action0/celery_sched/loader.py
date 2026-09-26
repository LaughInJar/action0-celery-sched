"""
Read schedules and turn them into Celery's ``beat_schedule`` setting.

A schedule is a mapping of entry names to entries (see
:py:mod:`~action0.celery_sched.entries`), written in YAML or TOML (see
:py:mod:`~action0.celery_sched.formats`) or handed over as a mapping (see
:py:mod:`~action0.celery_sched.sources`); an empty file is an empty
schedule. Entries whose name starts with a ``.`` are *templates*: they are
never scheduled. In YAML, that makes them the place for anchors that other
entries merge in:

.. code-block:: yaml

    .reports: &reports
      task: myapp.reports.tasks.build
      options: {queue: reports}

    "Daily report":
      <<: *reports
      kw: {period: day}
      schedule: {crontab: "@daily"}
"""

from typing import NoReturn

from action0.celery_sched.entries import BeatEntry
from action0.celery_sched.entries import Entry
from action0.celery_sched.entries import parse_entry
from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import DuplicateEntryError
from action0.celery_sched.errors import located
from action0.celery_sched.formats import FormatLike
from action0.celery_sched.sources import Source
from action0.celery_sched.sources import read_source
from action0.celery_sched.values import expect_mapping


def load_beat_schedule(
    *sources: Source, replace: bool = False, format: FormatLike | None = None
) -> dict[str, BeatEntry]:
    """
    Read schedules into a value for Celery's ``beat_schedule`` setting.

    Entries with ``enabled: false`` are left out::

        app.conf.beat_schedule = load_beat_schedule("beat.yaml")  # or "beat.toml"

    >>> load_beat_schedule({"Poll feed": {"task": "myapp.tasks.poll", "schedule": {"every": "5m"}}})
    {'Poll feed': {'task': 'myapp.tasks.poll', 'schedule': <freq: 5.00 minutes>, 'args': (), 'kwargs': {}, 'options': {}}}

    :param sources: the files, streams or mappings to read, merged in order
        (see :py:func:`load_entries`)
    :param replace: let a later source redefine an entry instead of raising
    :param format: the format of every file and stream, instead of telling it
        from their names (see :py:mod:`~action0.celery_sched.formats`)
    :returns: entry name → beat entry, in file order
    :raises DefinitionError: if a file or an entry is malformed
    :raises DuplicateEntryError: if two entries share a name
    :raises ValueError: if the format of a file or stream can't be told
    """
    entries = load_entries(*sources, replace=replace, format=format)
    return {entry.name: entry.to_celery() for entry in entries if entry.enabled}


def load_entries(
    *sources: Source, replace: bool = False, format: FormatLike | None = None
) -> list[Entry]:
    """
    Read and validate the entries of one or more schedules.

    Unlike :py:func:`load_beat_schedule`, disabled entries are included, and
    each one knows the file it came from — handy for tooling and tests.

    Sources are merged in order, whatever their format. An entry name defined
    twice is an error; with ``replace=True`` the later definition wins
    instead (keeping the position of the first), so an environment-specific
    file can override or disable entries of a shared one.

    :param sources: the files, streams or mappings to read
    :param replace: let a later source redefine an entry instead of raising
    :param format: the format of every file and stream, instead of telling it
        from their names
    :returns: the entries, in file order
    :raises DefinitionError: if a file or an entry is malformed
    :raises DuplicateEntryError: if two entries share a name
    :raises ValueError: if the format of a file or stream can't be told
    """
    merged: dict[str, Entry] = {}
    for source in sources:
        name, document = read_source(source, format)
        for entry in _parse_document(document, source=name):
            previous = merged.get(entry.name)
            if previous is not None and not replace:
                _raise_duplicate(entry, previous)
            merged[entry.name] = entry
    return list(merged.values())


def _parse_document(document: object, *, source: str | None) -> list[Entry]:
    """Validate the entries of one parsed document, whatever its format."""
    with located(source=source):
        if document is None:  # an empty YAML file, or one holding only comments
            return []
        if not isinstance(document, dict):
            raise DefinitionError("the top level must be a mapping of entry names")
        return [
            parse_entry(entry_name, value, source=source)
            for entry_name, value in expect_mapping(document).items()
            if not entry_name.startswith(".")  # a template, only there for its anchor
        ]


def _raise_duplicate(entry: Entry, previous: Entry) -> NoReturn:
    """Report an entry name that an earlier source already defined."""
    where = f" in {previous.source}" if previous.source is not None else ""
    error = DuplicateEntryError(f"already defined{where} (pass replace=True to override)")
    error.entry, error.source = entry.name, entry.source
    raise error
