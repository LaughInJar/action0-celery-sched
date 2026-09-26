import unittest

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.errors import DuplicateEntryError
from action0.celery_sched.errors import ScheduleError
from action0.celery_sched.errors import UnknownTaskError
from action0.celery_sched.errors import located


class DefinitionErrorTestCase(unittest.TestCase):
    """
    tests for :py:class:`~action0.celery_sched.errors.DefinitionError`
    """

    def test_reason_only(self) -> None:
        """
        Test that an error without a location renders as its reason.
        """
        self.assertEqual(str(DefinitionError("broken")), "broken")

    def test_full_location(self) -> None:
        """
        Test that source, entry and path are rendered in front of the reason.
        """
        error = DefinitionError("broken")
        error.source, error.entry, error.path = "beat.yaml", "Poll", ("schedule", "every")
        self.assertEqual(str(error), "beat.yaml: entry 'Poll': schedule.every: broken")

    def test_hierarchy(self) -> None:
        """
        Test that every error derives from ScheduleError.
        """
        self.assertTrue(issubclass(DefinitionError, ScheduleError))
        self.assertTrue(issubclass(DuplicateEntryError, DefinitionError))
        self.assertTrue(issubclass(UnknownTaskError, ScheduleError))


class LocatedTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.errors.located`
    """

    def test_nested_keys_build_the_path(self) -> None:
        """
        Test that nested blocks prepend their keys outermost-first.
        """
        with self.assertRaises(DefinitionError) as caught:
            with located("schedule"):
                with located("crontab", "hour"):
                    raise DefinitionError("broken")
        self.assertEqual(caught.exception.path, ("schedule", "crontab", "hour"))

    def test_innermost_entry_and_source_win(self) -> None:
        """
        Test that an outer block does not overwrite an entry or source set further in.
        """
        with self.assertRaises(DefinitionError) as caught:
            with located(entry="outer", source="outer.yaml"):
                with located(entry="inner", source="inner.yaml"):
                    raise DefinitionError("broken")
        self.assertEqual(caught.exception.entry, "inner")
        self.assertEqual(caught.exception.source, "inner.yaml")

    def test_other_exceptions_pass_through(self) -> None:
        """
        Test that exceptions other than DefinitionError are left alone.
        """
        with self.assertRaises(KeyError):
            with located("schedule"):
                raise KeyError("x")


class UnknownTaskErrorTestCase(unittest.TestCase):
    """
    tests for :py:class:`~action0.celery_sched.errors.UnknownTaskError`
    """

    def test_lists_every_missing_task(self) -> None:
        """
        Test that the message and the attribute hold all offenders.
        """
        error = UnknownTaskError({"A": "app.a", "B": "app.b"})
        self.assertEqual(error.missing, {"A": "app.a", "B": "app.b"})
        self.assertEqual(str(error), "unregistered tasks: 'A' -> app.a, 'B' -> app.b")
