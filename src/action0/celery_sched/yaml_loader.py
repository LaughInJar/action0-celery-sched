"""
The YAML loader for schedule files: PyYAML's ``SafeLoader``, plus two things.

- The ``!ENV`` tag substitutes environment variables into a scalar (see
  :py:mod:`~action0.celery_sched.envvars`).
- Duplicate keys are an error. Plain YAML parsers silently keep the *last*
  of two equal keys, so a copy-pasted entry that kept its name would quietly
  replace the original. Keys brought in through a merge (``<<: *base``) may
  still be overridden — that is what merging is for.

Being a ``SafeLoader``, it cannot instantiate arbitrary Python objects.
:py:func:`load_yaml` is the entry point the loaders use.
"""

from typing import Any

import yaml

from action0.celery_sched.envvars import substitute_env
from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import DuplicateEntryError

_MERGE_TAG = "tag:yaml.org,2002:merge"


class ScheduleLoader(yaml.SafeLoader):
    """
    ``SafeLoader`` with the ``!ENV`` tag and duplicate-key detection.

    >>> yaml.load("a: 1\\na: 2", Loader=ScheduleLoader)
    Traceback (most recent call last):
    ...
    action0.celery_sched.errors.DuplicateEntryError: duplicate entry 'a' on line 2 (first on line 1)
    """

    def __init__(self, stream: Any) -> None:
        """
        :param stream: the YAML text or stream
        """
        super().__init__(stream)
        # the nodes whose keys were checked; see flatten_mapping()
        self._checked: set[int] = set()
        self._root: yaml.Node | None = None

    def construct_document(self, node: yaml.Node) -> Any:
        """Remember the root, so a duplicate *entry* can be told from a duplicate key."""
        self._root = node
        return super().construct_document(node)

    def flatten_mapping(self, node: yaml.MappingNode) -> None:
        """
        Check a mapping's own keys for duplicates, then resolve its merges.

        This is the one hook PyYAML calls on every mapping *before* it
        rewrites the node's pairs to include the merged ones. A node can be
        flattened more than once (as a merge source, then again when
        constructed), so each is checked only on its first, untouched visit.
        """
        if id(node) not in self._checked:
            self._checked.add(id(node))
            self._check_duplicates(node)
        super().flatten_mapping(node)

    def _check_duplicates(self, node: yaml.MappingNode) -> None:
        """Raise on the first scalar key that appears twice in the node."""
        first_lines: dict[tuple[str, str], int] = {}
        for key_node, _value_node in node.value:
            if not isinstance(key_node, yaml.ScalarNode) or key_node.tag == _MERGE_TAG:
                continue
            key = (key_node.tag, key_node.value)
            line = key_node.start_mark.line + 1
            if key in first_lines:
                at_root = node is self._root
                error_type = DuplicateEntryError if at_root else DefinitionError
                raise error_type(
                    f"duplicate {'entry' if at_root else 'key'} {key_node.value!r} "
                    f"on line {line} (first on line {first_lines[key]})"
                )
            first_lines[key] = line


def load_yaml(text: str) -> Any:
    """
    Parse YAML text with the :py:class:`ScheduleLoader`.

    >>> load_yaml("'Poll feed': {schedule: {every: 5m}}")
    {'Poll feed': {'schedule': {'every': '5m'}}}

    :param text: the YAML document
    :returns: the parsed document (``None`` for an empty one)
    :raises DefinitionError: on a syntax error, a duplicate key, or an unset
        environment variable
    """
    try:
        return yaml.load(text, Loader=ScheduleLoader)
    except yaml.YAMLError as error:
        raise DefinitionError(f"invalid YAML: {error}") from error


def _env_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    """Construct an ``!ENV``-tagged scalar by substituting environment variables."""
    line = node.start_mark.line + 1
    if not isinstance(node, yaml.ScalarNode):
        raise DefinitionError(f"!ENV only applies to scalars (line {line})")
    try:
        return substitute_env(loader.construct_scalar(node))
    except DefinitionError as error:
        # the entry and key aren't known while parsing, but the line is
        raise DefinitionError(f"{error.reason} on line {line}") from None


ScheduleLoader.add_constructor("!ENV", _env_constructor)
