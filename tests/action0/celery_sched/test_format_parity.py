import io
import os
import unittest
from unittest import mock

from celery.schedules import schedule

from action0.celery_sched.entries import Entry
from action0.celery_sched.loader import load_beat_schedule
from action0.celery_sched.loader import load_entries

# one schedule using every feature an entry has, written in both formats
FULL_YAML = """\
.reports: &reports
  task: myapp.reports.tasks.build
  options: {queue: reports, priority: 5}

"Poll feed":
  task: myapp.feeds.tasks.poll
  schedule: {every: !ENV "${ACTION0_TEST_POLL:-5m}"}

"Hourly sync":
  task: myapp.sync.tasks.run
  params: [full, 3]
  schedule: {every: {hours: 1}, relative: true}

"Daily report":
  <<: *reports
  kw: {period: day, formats: [pdf, csv], limits: {rows: 100}}
  schedule: {crontab: "30 7 * * mon-fri"}

"Weekly report":
  <<: *reports
  kw: {period: week}
  schedule: {crontab: {minute: [0, 30], hour: 7, day_of_week: mon}}

"Sunset lights":
  task: myapp.home.tasks.lights_on
  schedule: {solar: {event: sunset, lat: 48.21, lon: 16.37}}
  enabled: !ENV ${ACTION0_TEST_LIGHTS:-false}
"""

FULL_TOML = """\
["Poll feed"]
task = "myapp.feeds.tasks.poll"
schedule = { every = "!ENV ${ACTION0_TEST_POLL:-5m}" }

["Hourly sync"]
task = "myapp.sync.tasks.run"
params = ["full", 3]
schedule = { every = { hours = 1 }, relative = true }

["Daily report"]
task = "myapp.reports.tasks.build"
kw = { period = "day", formats = ["pdf", "csv"], limits = { rows = 100 } }
schedule = { crontab = "30 7 * * mon-fri" }
options = { queue = "reports", priority = 5 }

["Weekly report"]
task = "myapp.reports.tasks.build"
schedule = { crontab = { minute = [0, 30], hour = 7, day_of_week = "mon" } }
options = { queue = "reports", priority = 5 }

["Weekly report".kw]
period = "week"

["Sunset lights"]
task = "myapp.home.tasks.lights_on"
schedule = { solar = { event = "sunset", lat = 48.21, lon = 16.37 } }
enabled = "!ENV ${ACTION0_TEST_LIGHTS:-false}"
"""


def _load(text: str, name: str) -> list[Entry]:
    stream = io.StringIO(text)
    stream.name = name
    return load_entries(stream)


class FormatParityTestCase(unittest.TestCase):
    """
    tests that a schedule means the same whether it is written in YAML or TOML
    """

    def assertSameEntries(self, first: list[Entry], second: list[Entry]) -> None:
        """
        Assert two entry lists are equal, including what schedule equality ignores.
        """
        self.assertEqual(first, second)
        for one, other in zip(first, second, strict=True):
            # celery's schedule compares its interval only, not the relative flag
            if isinstance(one.schedule, schedule) and isinstance(other.schedule, schedule):
                self.assertEqual(one.schedule.relative, other.schedule.relative, one.name)
            self.assertEqual(type(one.schedule), type(other.schedule), one.name)

    def test_same_entries(self) -> None:
        """
        Test that both spellings give equal entries, fallbacks of !ENV included.
        """
        with mock.patch.dict(os.environ, clear=False) as environ:
            environ.pop("ACTION0_TEST_POLL", None)
            environ.pop("ACTION0_TEST_LIGHTS", None)
            from_yaml = _load(FULL_YAML, "beat.yaml")
            from_toml = _load(FULL_TOML, "beat.toml")
        self.assertEqual(len(from_yaml), 5)
        self.assertSameEntries(from_yaml, from_toml)

    def test_same_entries_with_environment(self) -> None:
        """
        Test that both spellings of !ENV substitute the same variables.
        """
        environ = {"ACTION0_TEST_POLL": "90", "ACTION0_TEST_LIGHTS": "yes"}
        with mock.patch.dict(os.environ, environ):
            from_yaml = _load(FULL_YAML, "beat.yaml")
            from_toml = _load(FULL_TOML, "beat.toml")
        self.assertSameEntries(from_yaml, from_toml)
        self.assertTrue(from_toml[-1].enabled)

    def test_same_beat_schedule(self) -> None:
        """
        Test that the celery rendering is equal too.
        """
        from_yaml = load_beat_schedule(io.StringIO(FULL_YAML), format="yaml")
        from_toml = load_beat_schedule(io.StringIO(FULL_TOML), format="toml")
        self.assertEqual(from_yaml, from_toml)

    def test_same_as_mapping(self) -> None:
        """
        Test that the parsed data handed over as a mapping means the same again.
        """
        import tomllib

        from_toml = _load(FULL_TOML, "beat.toml")
        mapping = tomllib.loads(FULL_TOML.replace("!ENV ${ACTION0_TEST_POLL:-5m}", "5m"))
        mapping["Sunset lights"]["enabled"] = False
        self.assertSameEntries(load_entries(mapping), from_toml)
