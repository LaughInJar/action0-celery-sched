import sys
import unittest
from unittest import mock

from celery.schedules import solar

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.solar import SolarEvent
from action0.celery_sched.solar import parse_solar


class SolarEventTestCase(unittest.TestCase):
    """
    tests for :py:class:`~action0.celery_sched.solar.SolarEvent`
    """

    def test_matches_celery(self) -> None:
        """
        Test that the enum lists exactly the events Celery supports.
        """
        # _all_events is private (and not in the stubs), but it is the list Celery checks
        self.assertEqual({event.value for event in SolarEvent}, getattr(solar, "_all_events"))


class ParseSolarTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.solar.parse_solar`
    """

    def test_builds_schedule(self) -> None:
        """
        Test that event and coordinates reach the Celery schedule, string numbers included.
        """
        schedule = parse_solar({"event": "sunrise", "lat": "48.21", "lon": -16})
        self.assertIsInstance(schedule, solar)
        self.assertEqual((schedule.event, schedule.lat, schedule.lon), ("sunrise", 48.21, -16))

    def test_boundaries_are_valid(self) -> None:
        """
        Test that the poles and the date line are accepted.
        """
        parse_solar({"event": "solar_noon", "lat": -90, "lon": 180})

    def test_rejects_unknown_event(self) -> None:
        """
        Test that an unknown event is reported with the choices.
        """
        with self.assertRaises(DefinitionError) as caught:
            parse_solar({"event": "noon", "lat": 0, "lon": 0})
        self.assertEqual(caught.exception.path, ("event",))
        self.assertIn("solar_noon", caught.exception.reason)

    def test_rejects_out_of_range(self) -> None:
        """
        Test that latitude and longitude are range-checked.
        """
        for key, value in (("lat", 90.5), ("lat", "-91"), ("lon", 181), ("lon", "nan")):
            with self.subTest(key=key, value=value):
                node: dict[str, object] = {"event": "sunset", "lat": 0, "lon": 0, key: value}
                with self.assertRaises(DefinitionError) as caught:
                    parse_solar(node)
                self.assertEqual(caught.exception.path, (key,))

    def test_requires_all_keys(self) -> None:
        """
        Test that event, lat and lon are all required, and nothing else allowed.
        """
        with self.assertRaisesRegex(DefinitionError, "missing required key 'lon'"):
            parse_solar({"event": "sunset", "lat": 0})
        with self.assertRaisesRegex(DefinitionError, "unknown key 'elevation'"):
            parse_solar({"event": "sunset", "lat": 0, "lon": 0, "elevation": 100})

    def test_missing_ephem(self) -> None:
        """
        Test that a missing ephem is explained with the extra to install.
        """
        # a None entry in sys.modules makes the import raise ImportError
        with mock.patch.dict(sys.modules, {"ephem": None}):
            with self.assertRaisesRegex(ImportError, r"action0-celery-sched\[solar\]"):
                parse_solar({"event": "sunset", "lat": 0, "lon": 0})
