"""
The file formats a schedule can be written in, and how the loaders tell them apart.

A schedule means the same whatever its format — the entries have the same
keys and values — so the format only decides which parser turns the text into
data. By default a file's suffix decides: ``.yaml`` and ``.yml`` are YAML,
``.toml`` is TOML. A stream is judged by its ``name`` (which files opened with
:py:func:`open` have); anything else needs an explicit ``format``.

TOML is read with the standard library's :py:mod:`tomllib`. YAML needs
PyYAML, which comes with the ``yaml`` extra
(``pip install "action0-celery-sched[yaml]"``); it is imported only once a
YAML source is actually read, so TOML-only installs never need it.
"""

from collections.abc import Callable
from enum import StrEnum
from pathlib import PurePath
from typing import Any
from typing import Literal
from typing import TypeAlias

from action0.celery_sched.toml_loader import load_toml


class Format(StrEnum):
    """
    A file format for schedules.

    >>> Format("toml") is Format.TOML
    True
    """

    YAML = "yaml"
    TOML = "toml"


#: a :py:class:`Format`, or its value as a plain string
FormatLike: TypeAlias = Format | Literal["yaml", "toml"]

#: the file suffixes each format is recognised by (compared case-insensitively)
SUFFIXES: dict[str, Format] = {
    ".yaml": Format.YAML,
    ".yml": Format.YAML,
    ".toml": Format.TOML,
}


def detect_format(name: str | None, format: FormatLike | None = None) -> Format:
    """
    Decide the format of a file: the explicit one if given, else by its suffix.

    >>> detect_format("conf/beat.toml")
    <Format.TOML: 'toml'>
    >>> detect_format(None, "yaml")
    <Format.YAML: 'yaml'>

    :param name: the file name or path, ``None`` for an unnamed stream
    :param format: the format to use regardless of the name
    :returns: the format
    :raises ValueError: if ``format`` is not a known format, or it isn't given
        and the name doesn't end in a known suffix
    """
    if format is not None:
        try:
            return Format(format)
        except ValueError:
            raise ValueError(f"unknown format {format!r} (choose from: {_choices()})") from None
    suffix = PurePath(name).suffix.lower() if name is not None else ""
    if suffix in SUFFIXES:
        return SUFFIXES[suffix]
    explicit = " or ".join(f"format={choice.value!r}" for choice in Format)
    if name is None:
        raise ValueError(f"cannot tell the format of an unnamed stream: pass {explicit}")
    known = ", ".join(SUFFIXES)
    raise ValueError(
        f"cannot tell the format of {name!r} (known suffixes: {known}): pass {explicit}"
    )


def parse_text(text: str, format: Format) -> Any:
    """
    Parse schedule text in the given format.

    >>> parse_text("[Poll]\\ntask = 'myapp.tasks.poll'", Format.TOML)
    {'Poll': {'task': 'myapp.tasks.poll'}}

    :param text: the document
    :param format: its format
    :returns: the parsed document, as plain Python data
    :raises DefinitionError: if the text is malformed
    :raises ImportError: for YAML, if PyYAML (the ``yaml`` extra) is not installed
    """
    return parser_for(format)(text)


def parser_for(format: Format) -> Callable[[str], Any]:
    """
    Get the parser of a format, importing the YAML one on first use.

    The loaders call this *before* reading a source, so a missing PyYAML is
    reported without any I/O, like a format that can't be told.

    >>> parser_for(Format.TOML).__name__
    'load_toml'

    :param format: the format
    :returns: a function turning text in that format into plain Python data
    :raises ImportError: for YAML, if PyYAML (the ``yaml`` extra) is not installed
    """
    if format is Format.TOML:
        return load_toml
    try:
        from action0.celery_sched.yaml_loader import load_yaml
    except ImportError as error:
        if error.name != "yaml":  # a real bug, not the missing extra
            raise
        raise ImportError(
            "YAML schedules need PyYAML: pip install 'action0-celery-sched[yaml]'"
        ) from error
    return load_yaml


def _choices() -> str:
    """The format values, for error messages."""
    return ", ".join(repr(choice.value) for choice in Format)
