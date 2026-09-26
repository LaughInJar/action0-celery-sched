import unittest
from typing import Any

from celery.schedules import crontab

from action0.celery_sched.entries import Entry
from action0.celery_sched.entries import parse_entry
from action0.celery_sched.errors import DefinitionError


def _node(**extra: Any) -> dict[str, Any]:
    """A minimal valid entry, plus whatever the test adds or overrides."""
    return {"task": "myapp.tasks.poll", "schedule": {"crontab": "@hourly"}, **extra}


class ParseEntryTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.entries.parse_entry`
    """

    def test_minimal_entry(self) -> None:
        """
        Test that task and schedule suffice, everything else defaulting to empty.
        """
        entry = parse_entry("Poll", _node(), source="beat.yaml")
        self.assertEqual(entry.name, "Poll")
        self.assertEqual(entry.task, "myapp.tasks.poll")
        self.assertEqual(entry.schedule, crontab(minute=0))
        self.assertEqual((entry.args, entry.kwargs, entry.options), ((), {}, {}))
        self.assertTrue(entry.enabled)
        self.assertEqual(entry.source, "beat.yaml")

    def test_full_entry(self) -> None:
        """
        Test that params, kw, options and enabled are taken over.
        """
        entry = parse_entry(
            "Report",
            _node(
                params=["daily", 2],
                kw={"recipients": ["ops@example.com"]},
                options={"queue": "reports", "expires": 600},
                enabled="false",
            ),
        )
        self.assertEqual(entry.args, ("daily", 2))
        self.assertEqual(entry.kwargs, {"recipients": ["ops@example.com"]})
        self.assertEqual(entry.options, {"queue": "reports", "expires": 600})
        self.assertFalse(entry.enabled)

    def test_empty_blocks(self) -> None:
        """
        Test that `params:`, `kw:` and `options:` left empty in YAML (null) mean none.
        """
        entry = parse_entry("Poll", _node(params=None, kw=None, options=None))
        self.assertEqual((entry.args, entry.kwargs, entry.options), ((), {}, {}))

    def test_task_is_stripped(self) -> None:
        """
        Test that surrounding whitespace doesn't end up in the task name.
        """
        self.assertEqual(
            parse_entry("Poll", _node(task=" myapp.tasks.poll ")).task, "myapp.tasks.poll"
        )

    def test_arguments_are_copied(self) -> None:
        """
        Test that entries sharing a mapping (as YAML anchors do) don't share it at runtime.
        """
        shared = {"items": [1]}
        first = parse_entry("A", _node(kw=shared))
        second = parse_entry("B", _node(kw=shared))
        first.kwargs["items"].append(2)
        self.assertEqual(second.kwargs, {"items": [1]})
        self.assertEqual(shared, {"items": [1]})

    def test_errors_are_located(self) -> None:
        """
        Test that each invalid key reports entry, source and path.
        """
        cases: dict[str, dict[str, Any]] = {
            "task": _node(task=""),
            "schedule": _node(schedule={}),
            "params": _node(params="daily"),
            "kw": _node(kw=["x"]),
            "options": _node(options="reports"),
            "enabled": _node(enabled="sometimes"),
        }
        for key, node in cases.items():
            with self.subTest(key=key):
                with self.assertRaises(DefinitionError) as caught:
                    parse_entry("Poll", node, source="beat.yaml")
                self.assertEqual(caught.exception.path[0], key)
                self.assertEqual(caught.exception.entry, "Poll")
                self.assertEqual(caught.exception.source, "beat.yaml")

    def test_rejects_unknown_and_missing_keys(self) -> None:
        """
        Test that typos are unknown keys and task/schedule are required.
        """
        with self.assertRaisesRegex(DefinitionError, "unknown key 'shedule'"):
            parse_entry("Poll", {"task": "x", "shedule": {}})
        with self.assertRaisesRegex(DefinitionError, "missing required key 'schedule'"):
            parse_entry("Poll", {"task": "x"})
        with self.assertRaisesRegex(DefinitionError, "missing required key 'task'"):
            parse_entry("Poll", {"schedule": {"every": 5}})

    def test_rejects_non_mapping(self) -> None:
        """
        Test that an entry must be a mapping, and says which entry it is.
        """
        with self.assertRaisesRegex(DefinitionError, "entry 'Poll': expected a mapping"):
            parse_entry("Poll", "myapp.tasks.poll")


class EntryTestCase(unittest.TestCase):
    """
    tests for :py:class:`~action0.celery_sched.entries.Entry`
    """

    def test_to_celery(self) -> None:
        """
        Test that the celery rendering uses Celery's key names.
        """
        entry = parse_entry("Report", _node(params=[1], kw={"k": 2}, options={"queue": "q"}))
        self.assertEqual(
            entry.to_celery(),
            {
                "task": "myapp.tasks.poll",
                "schedule": crontab(minute=0),
                "args": (1,),
                "kwargs": {"k": 2},
                "options": {"queue": "q"},
            },
        )

    def test_to_celery_is_fresh(self) -> None:
        """
        Test that mutating the rendering doesn't change the entry.
        """
        entry = parse_entry("Report", _node(kw={"items": [1]}))
        rendered = entry.to_celery()
        rendered["kwargs"]["items"].append(2)
        rendered["options"]["queue"] = "q"
        self.assertEqual(entry.kwargs, {"items": [1]})
        self.assertEqual(entry.options, {})

    def test_source_is_not_compared(self) -> None:
        """
        Test that the same entry read from two files compares equal.
        """
        self.assertEqual(
            parse_entry("Poll", _node(), source="a.yaml"),
            parse_entry("Poll", _node(), source="b.yaml"),
        )

    def test_is_frozen(self) -> None:
        """
        Test that entries are immutable.
        """
        entry = parse_entry("Poll", _node())
        with self.assertRaises(AttributeError):
            entry.task = "other"  # type: ignore[misc]  # ty: ignore[invalid-assignment]
        self.assertIsInstance(entry, Entry)
