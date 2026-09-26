import io
import tempfile
import textwrap
import unittest
from datetime import timedelta
from pathlib import Path

from celery import Celery
from celery.beat import Scheduler
from celery.schedules import crontab
from celery.schedules import schedule

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import DuplicateEntryError
from action0.celery_sched.loader import load_beat_schedule
from action0.celery_sched.loader import load_entries

SCHEDULE_YAML = """\
"Poll feed":
  task: myapp.feeds.tasks.poll
  schedule:
    every: 5m

"Nightly report":
  task: myapp.reports.tasks.nightly
  kw:
    recipients: [ops@example.com]
  params:
    - daily
  schedule:
    crontab: "0 3 * * *"
  options:
    queue: reports

"Retired":
  task: myapp.tasks.old
  schedule: {every: 1h}
  enabled: false
"""

SCHEDULE_TOML = """\
["Poll feed"]
task = "myapp.feeds.tasks.poll"
schedule = { every = "5m" }

["Nightly report"]
task = "myapp.reports.tasks.nightly"
kw = { recipients = ["ops@example.com"] }
params = ["daily"]
schedule = { crontab = "0 3 * * *" }
options = { queue = "reports" }

["Retired"]
task = "myapp.tasks.old"
schedule = { every = "1h" }
enabled = false
"""


def _stream(text: str, name: str | None = "beat.yaml") -> io.StringIO:
    """A text stream of dedented schedule text, named like a file unless name is None."""
    stream = io.StringIO(textwrap.dedent(text))
    if name is not None:
        stream.name = name
    return stream


class _FilesTestCase(unittest.TestCase):
    """
    a test case with a temporary directory to write schedule files to
    """

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def _write(self, name: str, text: str) -> Path:
        path = self.directory / name
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path


class FileTestCase(_FilesTestCase):
    """
    tests reading schedule files from disk
    """

    def test_path_and_str(self) -> None:
        """
        Test that both Path objects and strings are read as files.
        """
        path = self._write("beat.yaml", SCHEDULE_YAML)
        self.assertEqual(load_beat_schedule(path), load_beat_schedule(str(path)))
        self.assertEqual(load_entries(path)[0].source, str(path))

    def test_formats_by_suffix(self) -> None:
        """
        Test that .yaml, .yml and .toml files are each read in their format, alike.
        """
        expected = load_beat_schedule(self._write("beat.yaml", SCHEDULE_YAML))
        self.assertEqual(load_beat_schedule(self._write("beat.yml", SCHEDULE_YAML)), expected)
        self.assertEqual(load_beat_schedule(self._write("beat.toml", SCHEDULE_TOML)), expected)

    def test_format_overrides_suffix(self) -> None:
        """
        Test that an explicit format reads a file whatever it is called.
        """
        path = self._write("beat.conf", SCHEDULE_TOML)
        self.assertEqual(
            list(load_beat_schedule(path, format="toml")), ["Poll feed", "Nightly report"]
        )

    def test_unknown_suffix(self) -> None:
        """
        Test that a file of unknown format is refused before it is even opened.
        """
        with self.assertRaisesRegex(ValueError, "cannot tell the format"):
            load_beat_schedule(self.directory / "does-not-exist.conf")

    def test_errors_name_the_file(self) -> None:
        """
        Test that an error message starts with the file it is in, in either format.
        """
        cases = {
            "beat.yaml": '"Poll": {task: x, schedule: {every: soon}}',
            "beat.toml": '[Poll]\ntask = "x"\nschedule = { every = "soon" }',
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                path = self._write(name, text)
                with self.assertRaises(DefinitionError) as caught:
                    load_beat_schedule(path)
                self.assertTrue(
                    str(caught.exception).startswith(f"{path}: entry 'Poll': schedule.every:")
                )

    def test_missing_file(self) -> None:
        """
        Test that a missing file raises the usual OSError.
        """
        with self.assertRaises(FileNotFoundError):
            load_beat_schedule(self.directory / "nope.yaml")


class MergeTestCase(_FilesTestCase):
    """
    tests merging several sources
    """

    def test_merges_in_order(self) -> None:
        """
        Test that entries of several sources are merged in order, formats mixed.
        """
        base = self._write("base.yaml", '"A": {task: a, schedule: {every: 1}}')
        extra = self._write("extra.toml", '[B]\ntask = "b"\nschedule = { every = 2 }')
        mapping = {"C": {"task": "c", "schedule": {"every": 3}}}
        self.assertEqual(list(load_beat_schedule(base, extra, mapping)), ["A", "B", "C"])

    def test_duplicate_across_files(self) -> None:
        """
        Test that redefining an entry in a later file names both files.
        """
        base = self._write("base.yaml", '"A": {task: a, schedule: {every: 1}}')
        prod = self._write("prod.toml", '[A]\ntask = "b"\nschedule = { every = 2 }')
        with self.assertRaises(DuplicateEntryError) as caught:
            load_beat_schedule(base, prod)
        self.assertEqual(
            str(caught.exception),
            f"{prod}: entry 'A': already defined in {base} (pass replace=True to override)",
        )

    def test_duplicate_from_mapping(self) -> None:
        """
        Test that a mapping source, having no name, is left out of the message.
        """
        mapping = {"A": {"task": "a", "schedule": {"every": 1}}}
        with self.assertRaisesRegex(DuplicateEntryError, r"^entry 'A': already defined \("):
            load_beat_schedule(mapping, mapping)

    def test_replace(self) -> None:
        """
        Test that with replace=True a later file overrides or disables entries in place.
        """
        base = self._write(
            "base.yaml",
            """\
            "A": {task: a, schedule: {every: 1}}
            "B": {task: b, schedule: {every: 1}}
            "C": {task: c, schedule: {every: 1}}
            """,
        )
        prod = self._write(
            "prod.yaml",
            """\
            "A": {task: a, schedule: {every: 60}}
            "B": {task: b, schedule: {every: 1}, enabled: false}
            """,
        )
        result = load_beat_schedule(base, prod, replace=True)
        self.assertEqual(list(result), ["A", "C"])
        self.assertEqual(result["A"]["schedule"], schedule(timedelta(seconds=60)))
        self.assertEqual(
            [entry.source for entry in load_entries(base, prod, replace=True)],
            [str(prod), str(prod), str(base)],
        )

    def test_nothing_to_merge(self) -> None:
        """
        Test that no sources at all is an empty schedule.
        """
        self.assertEqual(load_beat_schedule(), {})


class DocumentTestCase(unittest.TestCase):
    """
    tests for the shape of a schedule document
    """

    def test_beat_schedule(self) -> None:
        """
        Test the celery rendering of a typical file, disabled entries left out.
        """
        result = load_beat_schedule(_stream(SCHEDULE_YAML))
        self.assertEqual(list(result), ["Poll feed", "Nightly report"])
        self.assertEqual(
            result["Nightly report"],
            {
                "task": "myapp.reports.tasks.nightly",
                "schedule": crontab(minute=0, hour=3),
                "args": ("daily",),
                "kwargs": {"recipients": ["ops@example.com"]},
                "options": {"queue": "reports"},
            },
        )

    def test_entries_include_disabled(self) -> None:
        """
        Test that load_entries keeps disabled entries.
        """
        entries = load_entries(_stream(SCHEDULE_YAML))
        self.assertEqual([entry.enabled for entry in entries], [True, True, False])
        self.assertEqual(entries[0].source, "beat.yaml")

    def test_empty_documents(self) -> None:
        """
        Test that empty files, or ones with only comments, are empty schedules.
        """
        for name, text in (("beat.yaml", ""), ("beat.yaml", "# none yet\n"), ("beat.toml", "")):
            with self.subTest(name=name, text=text):
                self.assertEqual(load_beat_schedule(_stream(text, name)), {})

    def test_templates_are_skipped(self) -> None:
        """
        Test that dot-prefixed entries are only there for their anchors.
        """
        text = """\
            .reports: &reports
              task: myapp.reports.tasks.build
              options: {queue: reports}
            "Daily report":
              <<: *reports
              kw: {period: day}
              schedule: {crontab: "@daily"}
        """
        result = load_beat_schedule(_stream(text))
        self.assertEqual(list(result), ["Daily report"])
        self.assertEqual(result["Daily report"]["options"], {"queue": "reports"})
        self.assertEqual(result["Daily report"]["kwargs"], {"period": "day"})

    def test_templates_need_not_be_valid_entries(self) -> None:
        """
        Test that a template holding only part of an entry is fine, in either format.
        """
        yaml_text = """\
            .queue: &queue {queue: reports}
            "Report": {task: r, schedule: {every: 1h}, options: *queue}
        """
        result = load_beat_schedule(_stream(yaml_text))
        self.assertEqual(result["Report"]["options"], {"queue": "reports"})
        toml_text = (
            '[".unused"]\nqueue = "reports"\n[Report]\ntask = "r"\nschedule = { every = 1 }'
        )
        self.assertEqual(list(load_beat_schedule(_stream(toml_text, "beat.toml"))), ["Report"])

    def test_top_level_must_be_mapping(self) -> None:
        """
        Test that a list or scalar document is rejected.
        """
        for text in ("- a\n- b\n", "just text\n"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(DefinitionError, "top level must be a mapping"):
                    load_beat_schedule(_stream(text))

    def test_invalid_syntax(self) -> None:
        """
        Test that a syntax error is a DefinitionError naming the file and format.
        """
        with self.assertRaisesRegex(DefinitionError, r"^beat\.yaml: invalid YAML"):
            load_beat_schedule(_stream('"Poll": {task: ['))
        with self.assertRaisesRegex(DefinitionError, r"^beat\.toml: invalid TOML"):
            load_beat_schedule(_stream("[Poll\n", "beat.toml"))

    def test_duplicate_within_file(self) -> None:
        """
        Test that a name used twice in one file is caught, not silently overwritten.
        """
        text = """\
            "Poll": {task: a, schedule: {every: 1}}
            "Poll": {task: b, schedule: {every: 2}}
        """
        with self.assertRaisesRegex(DuplicateEntryError, r"^beat\.yaml: duplicate entry 'Poll'"):
            load_beat_schedule(_stream(text))
        # TOML forbids it in its syntax already
        toml_text = '[Poll]\ntask = "a"\n[Poll]\ntask = "b"\n'
        with self.assertRaisesRegex(DefinitionError, r"^beat\.toml: invalid TOML"):
            load_beat_schedule(_stream(toml_text, "beat.toml"))


class CeleryIntegrationTestCase(unittest.TestCase):
    """
    tests that Celery's own beat scheduler accepts the loaded schedule
    """

    def test_scheduler_accepts_schedule(self) -> None:
        """
        Test that beat builds its entries from the setting unchanged, from either format.
        """
        for source in (_stream(SCHEDULE_YAML), _stream(SCHEDULE_TOML, "beat.toml")):
            with self.subTest(source=source.name):
                app = Celery("test", set_as_current=False)
                app.conf.beat_schedule = load_beat_schedule(source)
                scheduler = Scheduler(app)
                entry = scheduler.schedule["Nightly report"]
                self.assertEqual(entry.task, "myapp.reports.tasks.nightly")
                self.assertEqual(entry.args, ("daily",))
                self.assertEqual(entry.kwargs, {"recipients": ["ops@example.com"]})
                self.assertEqual(entry.options, {"queue": "reports"})
                self.assertEqual(entry.schedule, crontab(minute=0, hour=3))
                assert entry.schedule is not None
                self.assertIs(entry.schedule.app, app)
                self.assertNotIn("Retired", scheduler.schedule)

    def test_schedules_evaluate(self) -> None:
        """
        Test that beat can compute when each loaded schedule is due.
        """
        app = Celery("test", set_as_current=False)
        app.conf.beat_schedule = load_beat_schedule(_stream(SCHEDULE_YAML))
        for name, entry in Scheduler(app).schedule.items():
            with self.subTest(name=name):
                is_due, next_check = entry.is_due()
                self.assertIsInstance(is_due, bool)
                self.assertGreater(next_check, 0)
