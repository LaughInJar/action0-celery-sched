import unittest

from celery.schedules import crontab

from action0.celery_sched.crontabs import NICKNAMES
from action0.celery_sched.crontabs import parse_crontab
from action0.celery_sched.errors import DefinitionError


class CronStringTestCase(unittest.TestCase):
    """
    tests for crontabs given as a five-field cron string
    """

    def test_fields_in_cron_order(self) -> None:
        """
        Test that the fields map to minute, hour, day of month, month, day of week.
        """
        self.assertEqual(
            parse_crontab("15 7 1 6 mon"),
            crontab(minute=15, hour=7, day_of_month=1, month_of_year=6, day_of_week="mon"),
        )

    def test_whitespace_is_flexible(self) -> None:
        """
        Test that runs of spaces and tabs separate fields (Celery's from_string can't).
        """
        self.assertEqual(parse_crontab("  0   3\t* * * "), crontab(minute=0, hour=3))

    def test_nicknames(self) -> None:
        """
        Test that every nickname expands to its five-field equivalent.
        """
        for nickname, expanded in NICKNAMES.items():
            with self.subTest(nickname=nickname):
                self.assertEqual(parse_crontab(nickname), parse_crontab(expanded))
        self.assertEqual(parse_crontab("@HOURLY"), crontab(minute=0))

    def test_rejects_wrong_field_count(self) -> None:
        """
        Test that anything but five fields (or a nickname) is rejected.
        """
        for text in ("0 3 * *", "0 3 * * * *", "", "@sometimes"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(DefinitionError, "expected 5 fields"):
                    parse_crontab(text)

    def test_invalid_field_is_located(self) -> None:
        """
        Test that Celery's validation error is pinned to the offending field.
        """
        with self.assertRaises(DefinitionError) as caught:
            parse_crontab("0 25 * * *")
        self.assertEqual(caught.exception.path, ("hour",))
        self.assertIn("'25'", caught.exception.reason)


class MappingTestCase(unittest.TestCase):
    """
    tests for crontabs given as a mapping of Celery's arguments
    """

    def test_omitted_fields_are_wildcards(self) -> None:
        """
        Test that only the given fields are restricted.
        """
        self.assertEqual(
            parse_crontab({"minute": 30, "hour": 7, "day_of_week": "mon-fri"}),
            crontab(minute=30, hour=7, day_of_week="mon-fri"),
        )
        self.assertEqual(parse_crontab({}), crontab())

    def test_lists_of_numbers(self) -> None:
        """
        Test that a field may be a list of numbers.
        """
        self.assertEqual(parse_crontab({"minute": [0, 30]}), crontab(minute="0,30"))

    def test_rejects_unknown_field(self) -> None:
        """
        Test that a misspelled field name is rejected.
        """
        with self.assertRaisesRegex(DefinitionError, "unknown key 'weekday'"):
            parse_crontab({"weekday": "mon"})

    def test_rejects_bad_types(self) -> None:
        """
        Test that booleans, nulls, mappings and non-numeric lists are rejected.
        """
        for spec in (True, None, {"a": 1}, ["mon"], [1, True]):
            with self.subTest(spec=spec):
                with self.assertRaises(DefinitionError) as caught:
                    parse_crontab({"hour": spec})
                self.assertEqual(caught.exception.path, ("hour",))

    def test_invalid_field_is_located(self) -> None:
        """
        Test that out-of-range values are caught at load time, per field.
        """
        for field, spec in (("minute", 60), ("month_of_year", "13"), ("day_of_week", "fun")):
            with self.subTest(field=field):
                with self.assertRaises(DefinitionError) as caught:
                    parse_crontab({field: spec})
                self.assertEqual(caught.exception.path, (field,))

    def test_rejects_other_types(self) -> None:
        """
        Test that the value must be a string or a mapping.
        """
        with self.assertRaisesRegex(DefinitionError, "expected a mapping"):
            parse_crontab(5)
