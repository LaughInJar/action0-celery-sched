"""
The ``!ENV`` substitution: ``${VAR}`` and ``${VAR:-fallback}`` from the environment.

Substitution is purely textual and happens once, at load time: the result is
always a string and is *not* parsed as YAML again, so a value like ``"yes"``
or ``"0123"`` cannot change type behind your back. The validators accept the
string spellings of numbers and booleans for exactly that reason.
"""

import os
import re
from collections.abc import Mapping

from action0.celery_sched.errors import DefinitionError

# ${VAR} or ${VAR:-fallback}
_ENV_PATTERN = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<fallback>[^}]*))?\}")


def substitute_env(value: str, environ: Mapping[str, str] | None = None) -> str:
    """
    Replace ``${VAR}`` / ``${VAR:-fallback}`` occurrences from the environment.

    >>> substitute_env("${REPORT_HOUR:-3}", environ={})
    '3'
    >>> substitute_env("${QUEUE}-high", environ={"QUEUE": "reports"})
    'reports-high'

    :param value: the scalar tagged with ``!ENV``
    :param environ: where to look the variables up (default: :py:data:`os.environ`)
    :returns: the substituted string
    :raises DefinitionError: if a variable without fallback is not set
    """
    variables = os.environ if environ is None else environ

    def replace(match: "re.Match[str]") -> str:
        name = match["name"]
        env_value = variables.get(name)
        if env_value is not None:
            return env_value
        if match["fallback"] is not None:
            return match["fallback"]
        raise DefinitionError(f"environment variable {name!r} is not set (referenced via !ENV)")

    return _ENV_PATTERN.sub(replace, value)
