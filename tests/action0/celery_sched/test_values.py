import unittest

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.values import as_bool
from action0.celery_sched.values import as_number
from action0.celery_sched.values import check_keys
from action0.celery_sched.values import describe
from action0.celery_sched.values import expect_mapping


class DescribeTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.values.describe`
    """

    def test_long_values_are_shortened(self) -> None:
        """
        Test that a long repr is cut off with an ellipsis.
        """
        description = describe("x" * 100)
        self.assertTrue(description.startswith("str 'xxx"))
        self.assertTrue(description.endswith("..."))
        self.assertLess(len(description), 50)


class ExpectMappingTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.values.expect_mapping`
    """

    def test_rejects_non_mappings(self) -> None:
        """
        Test that lists and scalars are rejected.
        """
        for value in ([1], "text", 3, None):
            with self.subTest(value=value), self.assertRaises(DefinitionError):
                expect_mapping(value)

    def test_rejects_non_string_keys(self) -> None:
        """
        Test that a mapping with a non-string key is rejected.
        """
        with self.assertRaisesRegex(DefinitionError, "keys must be strings"):
            expect_mapping({1: "one"})


class CheckKeysTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.values.check_keys`
    """

    def test_accepts_known_keys(self) -> None:
        """
        Test that a mapping of allowed keys, required ones present, passes.
        """
        check_keys({"a": 1, "b": 2}, allowed=("a", "b", "c"), required=("a",))

    def test_rejects_unknown_key(self) -> None:
        """
        Test that an unknown key is reported along with the allowed ones.
        """
        with self.assertRaisesRegex(DefinitionError, r"unknown key 'x' \(allowed: a, b\)"):
            check_keys({"x": 1}, allowed=("b", "a"))

    def test_reports_missing_key(self) -> None:
        """
        Test that a missing required key is reported.
        """
        with self.assertRaisesRegex(DefinitionError, "missing required key 'a'"):
            check_keys({}, allowed=("a",), required=("a",))


class AsNumberTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.values.as_number`
    """

    def test_numbers_and_numeric_strings(self) -> None:
        """
        Test that numbers pass through and numeric strings are converted.
        """
        self.assertEqual(as_number(3), 3)
        self.assertEqual(as_number(2.5), 2.5)
        self.assertEqual(as_number(" 42 "), 42)
        self.assertIsInstance(as_number("42"), int)
        self.assertEqual(as_number("-1.5"), -1.5)

    def test_rejects_non_numbers(self) -> None:
        """
        Test that booleans, text and other types are rejected.
        """
        for value in (True, "five", None, [1]):
            with self.subTest(value=value), self.assertRaises(DefinitionError):
                as_number(value)


class AsBoolTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.values.as_bool`
    """

    def test_booleans_and_spellings(self) -> None:
        """
        Test that booleans and their string spellings are accepted.
        """
        for value in (True, "true", "Yes", "ON", "1"):
            with self.subTest(value=value):
                self.assertIs(as_bool(value), True)
        for value in (False, "false", "No", "off", "0"):
            with self.subTest(value=value):
                self.assertIs(as_bool(value), False)

    def test_rejects_anything_else(self) -> None:
        """
        Test that numbers and other strings are not booleans.
        """
        for value in (1, 0, "maybe", None):
            with self.subTest(value=value), self.assertRaises(DefinitionError):
                as_bool(value)
