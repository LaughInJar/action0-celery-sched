import datetime
import os
import unittest
from unittest import mock

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.toml_loader import load_toml


class LoadTomlTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.toml_loader.load_toml`
    """

    def test_parses_tables(self) -> None:
        """
        Test that quoted table names, inline tables and sub-tables all parse.
        """
        text = """\
["Nightly report"]
task = "myapp.reports.tasks.nightly"
schedule = { crontab = "0 3 * * *" }

["Nightly report".kw]
recipients = ["ops@example.com"]
"""
        self.assertEqual(
            load_toml(text),
            {
                "Nightly report": {
                    "task": "myapp.reports.tasks.nightly",
                    "schedule": {"crontab": "0 3 * * *"},
                    "kw": {"recipients": ["ops@example.com"]},
                }
            },
        )

    def test_empty(self) -> None:
        """
        Test that an empty document is an empty table.
        """
        self.assertEqual(load_toml(""), {})

    def test_syntax_error(self) -> None:
        """
        Test that TOML syntax errors, duplicates included, are DefinitionErrors.
        """
        for text in ("[Poll\n", "[Poll]\n[Poll]\n", "a = 1\na = 2\n"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(DefinitionError, "^invalid TOML: "):
                    load_toml(text)


class EnvPrefixTestCase(unittest.TestCase):
    """
    tests for the ``!ENV`` string prefix, TOML's spelling of the tag
    """

    def test_substitutes_everywhere(self) -> None:
        """
        Test that prefixed strings are substituted in nested tables and arrays.
        """
        text = """\
[Poll]
task = "!ENV ${ACTION0_TEST_TASK}"
params = ["!ENV ${ACTION0_TEST_ARG:-x}", "plain"]
schedule = { every = "!ENV\t${ACTION0_TEST_EVERY:-5m}" }
"""
        with mock.patch.dict(os.environ, {"ACTION0_TEST_TASK": "myapp.tasks.poll"}):
            document = load_toml(text)
        self.assertEqual(
            document,
            {
                "Poll": {
                    "task": "myapp.tasks.poll",
                    "params": ["x", "plain"],
                    "schedule": {"every": "5m"},
                }
            },
        )

    def test_only_the_prefix_counts(self) -> None:
        """
        Test that strings without the exact prefix, and keys, are left alone.
        """
        text = """\
[Poll]
a = "${HOME}"
b = "!ENV"
c = "!ENVIRONMENT ${HOME}"
d = "text !ENV ${HOME}"
"!ENV ${HOME}" = 1
"""
        self.assertEqual(
            load_toml(text)["Poll"],
            {
                "a": "${HOME}",
                "b": "!ENV",
                "c": "!ENVIRONMENT ${HOME}",
                "d": "text !ENV ${HOME}",
                "!ENV ${HOME}": 1,
            },
        )

    def test_non_strings_untouched(self) -> None:
        """
        Test that numbers, booleans and dates pass through.
        """
        document = load_toml("[Poll]\nn = 3\nb = true\nf = 1.5\nd = 2026-09-26\n")
        self.assertEqual(
            document["Poll"], {"n": 3, "b": True, "f": 1.5, "d": datetime.date(2026, 9, 26)}
        )

    def test_missing_variable_is_located(self) -> None:
        """
        Test that an unset variable reports the entry and key path it is in.
        """
        text = '[Poll]\nparams = ["a", "!ENV ${ACTION0_TEST_NOT_SET}"]\n'
        with mock.patch.dict(os.environ, clear=False) as environ:
            environ.pop("ACTION0_TEST_NOT_SET", None)
            with self.assertRaises(DefinitionError) as caught:
                load_toml(text)
        self.assertEqual(
            str(caught.exception),
            "entry 'Poll': params.1: environment variable 'ACTION0_TEST_NOT_SET' is not set "
            "(referenced via !ENV)",
        )
