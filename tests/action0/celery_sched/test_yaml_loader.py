import os
import textwrap
import unittest
from typing import Any
from unittest import mock

import yaml

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import DuplicateEntryError
from action0.celery_sched.yaml_loader import ScheduleLoader
from action0.celery_sched.yaml_loader import load_yaml


def _load(text: str) -> Any:
    """Parse dedented YAML with the schedule loader."""
    return yaml.load(textwrap.dedent(text), Loader=ScheduleLoader)


class DuplicateKeyTestCase(unittest.TestCase):
    """
    tests for the duplicate-key detection of the schedule loader
    """

    def test_duplicate_entry(self) -> None:
        """
        Test that two top-level entries of the same name are a DuplicateEntryError.
        """
        text = """\
            "Poll": {task: a}
            "Report": {task: b}
            "Poll": {task: c}
        """
        with self.assertRaisesRegex(
            DuplicateEntryError, r"duplicate entry 'Poll' on line 3 \(first on line 1\)"
        ):
            _load(text)

    def test_duplicate_nested_key(self) -> None:
        """
        Test that a duplicate key further down is a plain DefinitionError.
        """
        text = """\
            "Poll":
              kw:
                a: 1
                a: 2
        """
        with self.assertRaises(DefinitionError) as caught:
            _load(text)
        self.assertNotIsInstance(caught.exception, DuplicateEntryError)
        self.assertIn("duplicate key 'a' on line 4", str(caught.exception))

    def test_merged_keys_may_be_overridden(self) -> None:
        """
        Test that keys brought in by a merge can be overridden, as merging intends.
        """
        text = """\
            .base: &base {task: a, options: {queue: q}}
            "Poll":
              <<: *base
              task: b
        """
        self.assertEqual(_load(text)["Poll"], {"task": "b", "options": {"queue": "q"}})

    def test_chained_merges(self) -> None:
        """
        Test that a merge source which itself merges and overrides is no false duplicate.
        """
        text = """\
            .a: &a {task: a, kw: {x: 1}}
            "B": &b
              <<: *a
              task: b
            "C":
              <<: *b
            "D": *b
        """
        document = _load(text)
        self.assertEqual(document["C"], {"task": "b", "kw": {"x": 1}})
        self.assertEqual(document["D"], {"task": "b", "kw": {"x": 1}})

    def test_merge_source_flattened_before_construction(self) -> None:
        """
        Test that a node flattened as a merge source is not re-checked once rewritten.
        """
        text = """\
            "X":
              <<: &b {<<: {task: a}, task: b}
            "Y": *b
        """
        document = _load(text)
        self.assertEqual(document["X"], {"task": "b"})
        self.assertEqual(document["Y"], {"task": "b"})

    def test_equal_text_different_type(self) -> None:
        """
        Test that keys are compared by their resolved value, not just their text.
        """
        self.assertEqual(_load("'1': a\n1: b"), {"1": "a", 1: "b"})


class EnvTagTestCase(unittest.TestCase):
    """
    tests for the ``!ENV`` tag of the schedule loader
    """

    def test_substitutes_scalars(self) -> None:
        """
        Test that tagged scalars are substituted from the environment, as strings.
        """
        with mock.patch.dict(os.environ, {"ACTION0_TEST_EVERY": "300"}):
            document = _load("every: !ENV ${ACTION0_TEST_EVERY}\nhour: !ENV ${NOPE_NOT_SET:-3}")
        self.assertEqual(document, {"every": "300", "hour": "3"})

    def test_untagged_text_is_left_alone(self) -> None:
        """
        Test that ${...} without the tag stays literal.
        """
        self.assertEqual(_load("a: ${HOME}"), {"a": "${HOME}"})

    def test_rejects_collections(self) -> None:
        """
        Test that the tag is refused on sequences and mappings.
        """
        with self.assertRaisesRegex(DefinitionError, "only applies to scalars"):
            _load("a: !ENV [x]")

    def test_missing_variable_names_the_line(self) -> None:
        """
        Test that an unset variable is reported with the line it is used on.
        """
        with mock.patch.dict(os.environ, clear=False) as environ:
            environ.pop("ACTION0_TEST_NOT_SET", None)
            with self.assertRaisesRegex(
                DefinitionError,
                r"'ACTION0_TEST_NOT_SET' is not set \(referenced via !ENV\) on line 2$",
            ):
                _load("a: 1\nb: !ENV ${ACTION0_TEST_NOT_SET}")

    def test_safe(self) -> None:
        """
        Test that the loader is still a safe loader.
        """
        with self.assertRaises(yaml.YAMLError):
            _load("a: !!python/object/apply:os.getcwd []")


class LoadYamlTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.yaml_loader.load_yaml`
    """

    def test_parses(self) -> None:
        """
        Test that documents parse with the schedule loader, empty ones to None.
        """
        self.assertEqual(load_yaml("a: !ENV ${ACTION0_TEST_NOT_SET:-1}"), {"a": "1"})
        self.assertIsNone(load_yaml(""))

    def test_syntax_error(self) -> None:
        """
        Test that YAML errors become DefinitionErrors, keeping the original as cause.
        """
        with self.assertRaisesRegex(DefinitionError, "^invalid YAML: ") as caught:
            load_yaml("a: [")
        self.assertIsInstance(caught.exception.__cause__, yaml.YAMLError)

    def test_own_errors_pass_through(self) -> None:
        """
        Test that duplicate-key errors are not re-wrapped as syntax errors.
        """
        with self.assertRaises(DuplicateEntryError):
            load_yaml("a: 1\na: 2")
