"""
What the loaders read from, and turning each kind of source into data.

A source is one of:

- a path (a ``str`` or any path-like) to a YAML or TOML file;
- an open stream — text or binary, as :py:mod:`tomllib` users are used to;
- a mapping that is already the parsed document, e.g. a table of a larger
  TOML configuration, or a dict from a settings system.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import IO
from typing import Any
from typing import TypeAlias

from action0.celery_sched.errors import located
from action0.celery_sched.formats import FormatLike
from action0.celery_sched.formats import detect_format
from action0.celery_sched.formats import parser_for

#: what the load functions read from: a file path, an open stream, or parsed data
Source: TypeAlias = str | os.PathLike[str] | IO[str] | IO[bytes] | Mapping[str, Any]


def read_source(source: Source, format: FormatLike | None = None) -> tuple[str | None, Any]:
    """
    Read a source into its parsed document, and name it for error messages.

    >>> read_source({"Poll": {"task": "myapp.tasks.poll"}})
    (None, {'Poll': {'task': 'myapp.tasks.poll'}})

    :param source: the source to read
    :param format: the format of a file or stream, instead of guessing it from
        the name (ignored for mappings, which are parsed already)
    :returns: the source's name (the path, the stream's name, or ``None``) and
        its document
    :raises ValueError: if the format of a file or stream can't be told
    :raises ImportError: for a YAML source, if PyYAML (the ``yaml`` extra) is
        not installed
    :raises DefinitionError: if the text is malformed
    """
    if isinstance(source, Mapping):
        return None, source
    name = os.fspath(source) if isinstance(source, str | os.PathLike) else _stream_name(source)
    # decided before reading, so a file of unknown format (or one whose parser
    # isn't installed) fails without any I/O
    parse = parser_for(detect_format(name, format))
    text = _read_text(source)
    with located(source=name):
        return name, parse(text)


def _stream_name(stream: IO[str] | IO[bytes]) -> str | None:
    """The name of a stream, if it has a usable one (files opened with open() do)."""
    name = getattr(stream, "name", None)
    return name if isinstance(name, str) else None


def _read_text(source: str | os.PathLike[str] | IO[str] | IO[bytes]) -> str:
    """Read a file or a text or binary stream; schedules are UTF-8 (TOML requires it)."""
    if isinstance(source, str | os.PathLike):
        return Path(source).read_text(encoding="utf-8")
    content = source.read()
    return content.decode("utf-8") if isinstance(content, bytes) else content
