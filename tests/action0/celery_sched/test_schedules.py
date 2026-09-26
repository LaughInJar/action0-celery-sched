import unittest
from datetime import timedelta

from celery.schedules import crontab
from celery.schedules import schedule
from celery.schedules import solar

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.schedules import parse_schedule


class ParseScheduleTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.schedules.parse_schedule`
    """

    def test_every(self) -> None:
        """
        Test that an interval becomes a non-relative Celery schedule.
        """
        result = parse_schedule({"every": "90s"})
        # a schedule compares by its interval
        self.assertEqual(result, schedule(timedelta(seconds=90)))
        assert isinstance(result, schedule)
        self.assertFalse(result.relative)

    def test_every_relative(self) -> None:
        """
        Test that relative is passed on, also given as a string.
        """
        for relative in (True, "true"):
            with self.subTest(relative=relative):
                result = parse_schedule({"every": "1h", "relative": relative})
                assert isinstance(result, schedule)
                self.assertTrue(result.relative)

    def test_crontab(self) -> None:
        """
        Test that a crontab block becomes a Celery crontab.
        """
        self.assertEqual(parse_schedule({"crontab": "0 3 * * *"}), crontab(minute=0, hour=3))

    def test_solar(self) -> None:
        """
        Test that a solar block becomes a Celery solar schedule.
        """
        result = parse_schedule({"solar": {"event": "sunset", "lat": 48.2, "lon": 16.4}})
        self.assertIsInstance(result, solar)

    def test_requires_exactly_one_kind(self) -> None:
        """
        Test that zero or several kinds are rejected.
        """
        with self.assertRaisesRegex(DefinitionError, "got none"):
            parse_schedule({})
        with self.assertRaisesRegex(DefinitionError, "got every, crontab"):
            parse_schedule({"every": 5, "crontab": "@daily"})

    def test_rejects_unknown_kind(self) -> None:
        """
        Test that a misnamed kind is reported as an unknown key.
        """
        with self.assertRaisesRegex(DefinitionError, "unknown key 'interval'"):
            parse_schedule({"interval": "5m"})

    def test_relative_only_with_every(self) -> None:
        """
        Test that relative next to crontab or solar is rejected.
        """
        with self.assertRaisesRegex(DefinitionError, "'relative' only applies"):
            parse_schedule({"crontab": "@daily", "relative": True})

    def test_errors_are_located(self) -> None:
        """
        Test that errors inside a kind carry the kind in their path.
        """
        cases = {
            ("every",): {"every": "soon"},
            ("relative",): {"every": 5, "relative": "maybe"},
            ("crontab", "hour"): {"crontab": {"hour": 24}},
            ("solar", "event"): {"solar": {"event": "noon", "lat": 0, "lon": 0}},
        }
        for path, node in cases.items():
            with self.subTest(path=path):
                with self.assertRaises(DefinitionError) as caught:
                    parse_schedule(node)
                self.assertEqual(caught.exception.path, path)

    def test_rejects_scalars(self) -> None:
        """
        Test that the block must be a mapping — no inferred shorthand.
        """
        for value in ("5m", 30, "0 3 * * *"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(DefinitionError, "expected a mapping"):
                    parse_schedule(value)
