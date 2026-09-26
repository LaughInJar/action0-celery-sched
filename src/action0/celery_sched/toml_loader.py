"""
Parse TOML schedule files, with the standard library's :py:mod:`tomllib`.

An entry in TOML has exactly the keys and values it has in YAML:

.. code-block:: toml

    ["Nightly report"]
    task = "myapp.reports.tasks.nightly"
    params = ["daily"]
    kw = { recipients = ["ops@example.com"] }
    schedule = { crontab = "0 3 * * *" }
    options = { queue = "reports" }

TOML has no tags, so the ``!ENV`` substitution is written as a *prefix* of
a string: ``crontab = "!ENV ${REPORT_CRON:-0 3 * * *}"``. The rest of the
string, after ``!ENV`` and the whitespace following it, is substituted
exactly like YAML's ``!ENV`` tag does it (see
:py:mod:`~action0.celery_sched.envvars`). Only string values are
substituted, never keys.

TOML itself forbids declaring a key twice, so a duplicate entry is a syntax
error here.
"""

import re
import tomllib
from typing import Any

from action0.celery_sched.envvars import substitute_env
from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import located

# the TOML spelling of the !ENV tag: at the very start of a string
_ENV_PREFIX = re.compile(r"!ENV[ \t]+")


def load_toml(text: str) -> dict[str, Any]:
    """
    Parse TOML text and substitute its ``!ENV``-prefixed strings.

    >>> load_toml('["Poll feed"]\\nschedule = { every = "!ENV ${POLL_EVERY:-5m}" }')
    {'Poll feed': {'schedule': {'every': '5m'}}}

    :param text: the TOML document
    :returns: the parsed document
    :raises DefinitionError: on a syntax error, or an unset environment variable
    """
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise DefinitionError(f"invalid TOML: {error}") from None
    substituted: dict[str, Any] = {}
    for name, value in document.items():
        with located(entry=name):
            substituted[name] = _substitute(value)
    return substituted


def _substitute(value: Any) -> Any:
    """Substitute every ``!ENV``-prefixed string in a value, locating failures."""
    if isinstance(value, str):
        prefix = _ENV_PREFIX.match(value)
        return substitute_env(value[prefix.end() :]) if prefix else value
    if isinstance(value, dict):
        substituted: dict[str, Any] = {}
        for key, item in value.items():
            with located(key):
                substituted[key] = _substitute(item)
        return substituted
    if isinstance(value, list):
        items = []
        for index, item in enumerate(value):
            with located(str(index)):
                items.append(_substitute(item))
        return items
    return value
