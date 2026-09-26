import unittest
from datetime import timedelta

from action0.celery_sched.durations import parse_duration
from action0.celery_sched.errors import DefinitionError


class SecondsTestCase(unittest.TestCase):
    """
    tests for intervals given as a number of seconds
    """

    def test_numbers(self) -> None:
        """
        Test that ints and floats are seconds.
        """
        self.assertEqual(parse_duration(30), timedelta(seconds=30))
        self.assertEqual(parse_duration(2.5), timedelta(seconds=2.5))

    def test_numeric_strings(self) -> None:
        """
        Test that numeric strings (as !ENV produces them) are seconds too.
        """
        self.assertEqual(parse_duration("300"), timedelta(seconds=300))
        self.assertEqual(parse_duration("0.5"), timedelta(seconds=0.5))

    def test_rejects_non_positive(self) -> None:
        """
        Test that zero and negative intervals are rejected.
        """
        for value in (0, -5, "0", "-1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(DefinitionError, "must be positive"):
                    parse_duration(value)

    def test_rejects_infinite_and_huge(self) -> None:
        """
        Test that infinite or overflowing intervals are rejected.
        """
        with self.assertRaisesRegex(DefinitionError, "finite"):
            parse_duration(float("inf"))
        with self.assertRaisesRegex(DefinitionError, "finite"):
            parse_duration("nan")
        with self.assertRaisesRegex(DefinitionError, "too large"):
            parse_duration(10**20)

    def test_rejects_other_types(self) -> None:
        """
        Test that booleans, nulls and lists are rejected.
        """
        for value in (True, None, [5]):
            with self.subTest(value=value), self.assertRaises(DefinitionError):
                parse_duration(value)


class DurationStringTestCase(unittest.TestCase):
    """
    tests for intervals given as a duration string
    """

    def test_single_units(self) -> None:
        """
        Test every unit on its own.
        """
        cases = {
            "2w": timedelta(weeks=2),
            "1d": timedelta(days=1),
            "3h": timedelta(hours=3),
            "5m": timedelta(minutes=5),
            "90s": timedelta(seconds=90),
            "250ms": timedelta(milliseconds=250),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_duration(text), expected)

    def test_combinations_and_spacing(self) -> None:
        """
        Test that parts add up, with or without whitespace between them.
        """
        self.assertEqual(parse_duration("1h30m"), timedelta(minutes=90))
        self.assertEqual(parse_duration(" 2d 12h "), timedelta(hours=60))
        self.assertEqual(parse_duration("1 m 30 s"), timedelta(seconds=90))

    def test_fractions(self) -> None:
        """
        Test that fractional amounts are allowed.
        """
        self.assertEqual(parse_duration("1.5h"), timedelta(minutes=90))

    def test_rejects_malformed(self) -> None:
        """
        Test that unknown units, uppercase units and stray text are rejected.
        """
        for text in ("5 minutes", "5M", "1h30", "h", "", "every 5m", "5m!"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(DefinitionError, "expected seconds or a duration"):
                    parse_duration(text)

    def test_rejects_zero(self) -> None:
        """
        Test that a duration adding up to zero is rejected.
        """
        with self.assertRaisesRegex(DefinitionError, "must be positive"):
            parse_duration("0m0s")


class MappingTestCase(unittest.TestCase):
    """
    tests for intervals given as a mapping of timedelta arguments
    """

    def test_arguments(self) -> None:
        """
        Test that the mapping is passed to timedelta, string numbers included.
        """
        self.assertEqual(
            parse_duration({"hours": 1, "minutes": "30"}), timedelta(hours=1, minutes=30)
        )
        self.assertEqual(parse_duration({"milliseconds": 500}), timedelta(milliseconds=500))

    def test_rejects_unknown_and_empty(self) -> None:
        """
        Test that unknown keys (like months) and an empty mapping are rejected.
        """
        with self.assertRaisesRegex(DefinitionError, "unknown key 'months'"):
            parse_duration({"months": 1})
        with self.assertRaisesRegex(DefinitionError, "at least one of"):
            parse_duration({})

    def test_bad_value_is_located(self) -> None:
        """
        Test that a bad value reports the key it belongs to.
        """
        with self.assertRaises(DefinitionError) as caught:
            parse_duration({"hours": "soon"})
        self.assertEqual(caught.exception.path, ("hours",))
        with self.assertRaisesRegex(DefinitionError, "finite"):
            parse_duration({"hours": "inf"})

    def test_rejects_non_positive_and_huge(self) -> None:
        """
        Test that the mapping must add up to a positive, representable interval.
        """
        with self.assertRaisesRegex(DefinitionError, "must be positive"):
            parse_duration({"hours": 1, "minutes": -60})
        with self.assertRaisesRegex(DefinitionError, "too large"):
            parse_duration({"weeks": 10**12})
