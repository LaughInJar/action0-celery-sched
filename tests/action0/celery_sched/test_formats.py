import sys
import unittest
from unittest import mock

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.formats import Format
from action0.celery_sched.formats import detect_format
from action0.celery_sched.formats import parse_text
from action0.celery_sched.formats import parser_for
from action0.celery_sched.toml_loader import load_toml
from action0.celery_sched.yaml_loader import load_yaml


class DetectFormatTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.formats.detect_format`
    """

    def test_by_suffix(self) -> None:
        """
        Test that the known suffixes decide, case-insensitively and in any directory.
        """
        cases = {
            "beat.yaml": Format.YAML,
            "conf/beat.yml": Format.YAML,
            "/etc/myapp/beat.toml": Format.TOML,
            "BEAT.TOML": Format.TOML,
            "beat.prod.yaml": Format.YAML,
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertIs(detect_format(name), expected)

    def test_explicit_format_wins(self) -> None:
        """
        Test that a given format overrides the suffix, as an enum or a string.
        """
        self.assertIs(detect_format("beat.yaml", Format.TOML), Format.TOML)
        self.assertIs(detect_format("beat.conf", "yaml"), Format.YAML)
        self.assertIs(detect_format(None, "toml"), Format.TOML)

    def test_unknown_suffix(self) -> None:
        """
        Test that an unknown or missing suffix asks for an explicit format.
        """
        for name in ("beat.json", "beat", "<stdin>"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    ValueError,
                    rf"cannot tell the format of '{name}' \(known suffixes: .yaml, .yml, .toml\)",
                ):
                    detect_format(name)

    def test_unnamed_stream(self) -> None:
        """
        Test that a stream without a name needs an explicit format.
        """
        with self.assertRaisesRegex(
            ValueError, "an unnamed stream: pass format='yaml' or format='toml'$"
        ):
            detect_format(None)

    def test_unknown_format(self) -> None:
        """
        Test that an unknown format value is refused with the choices.
        """
        with self.assertRaisesRegex(
            ValueError, r"unknown format 'json' \(choose from: 'yaml', 'toml'\)"
        ):
            detect_format("beat.yaml", "json")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


class ParseTextTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.formats.parse_text`
    """

    def test_dispatches(self) -> None:
        """
        Test that each format goes to its own parser, giving the same data.
        """
        self.assertEqual(
            parse_text('Poll: {task: "myapp.tasks.poll"}', Format.YAML),
            parse_text('Poll = { task = "myapp.tasks.poll" }', Format.TOML),
        )

    def test_wrong_format(self) -> None:
        """
        Test that YAML parsed as TOML is a TOML syntax error.
        """
        with self.assertRaisesRegex(DefinitionError, "invalid TOML"):
            parse_text("Poll:\n  task: x\n", Format.TOML)


class ParserForTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.formats.parser_for`
    """

    def test_parsers(self) -> None:
        """
        Test that each format gets its own loader.
        """
        self.assertIs(parser_for(Format.TOML), load_toml)
        self.assertIs(parser_for(Format.YAML), load_yaml)

    def test_missing_pyyaml(self) -> None:
        """
        Test that YAML without PyYAML is explained with the extra to install.
        """
        # a None entry makes "import yaml" fail as if PyYAML weren't installed;
        # dropping the cached loader forces it to be imported again
        with mock.patch.dict(sys.modules, {"yaml": None}):
            del sys.modules["action0.celery_sched.yaml_loader"]
            with self.assertRaisesRegex(
                ImportError, r"^YAML schedules need PyYAML: .*action0-celery-sched\[yaml\]"
            ) as caught:
                parser_for(Format.YAML)
            self.assertIs(parser_for(Format.TOML), load_toml)
        self.assertEqual(getattr(caught.exception.__cause__, "name", None), "yaml")

    def test_other_import_errors_pass_through(self) -> None:
        """
        Test that an ImportError that isn't about PyYAML is not disguised as one.
        """
        with mock.patch.dict(sys.modules, {"action0.celery_sched.yaml_loader": None}):
            with self.assertRaises(ImportError) as caught:
                parser_for(Format.YAML)
        self.assertNotIn("need PyYAML", str(caught.exception))
