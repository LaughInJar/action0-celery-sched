import unittest

from celery import Celery

from action0.celery_sched.errors import UnknownTaskError
from action0.celery_sched.tasks import check_tasks


def _app() -> Celery:
    """An app with a single task registered as ``myapp.tasks.poll``."""
    app = Celery("test", set_as_current=False)

    @app.task(name="myapp.tasks.poll")
    def poll() -> None:
        pass

    return app


class CheckTasksTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.tasks.check_tasks`
    """

    def test_registered_tasks_pass(self) -> None:
        """
        Test that a schedule of registered tasks passes.
        """
        check_tasks(_app(), {"Poll": {"task": "myapp.tasks.poll"}})

    def test_reports_every_unregistered_task(self) -> None:
        """
        Test that all offenders are reported at once, the registered ones not.
        """
        schedule = {
            "Poll": {"task": "myapp.tasks.poll"},
            "Report": {"task": "myapp.tasks.report"},
            "Typo": {"task": "myapp.task.poll"},
        }
        with self.assertRaises(UnknownTaskError) as caught:
            check_tasks(_app(), schedule)
        self.assertEqual(
            caught.exception.missing,
            {"Report": "myapp.tasks.report", "Typo": "myapp.task.poll"},
        )

    def test_defaults_to_beat_schedule(self) -> None:
        """
        Test that the app's own beat_schedule setting is checked by default.
        """
        app = _app()
        app.conf.beat_schedule = {"Report": {"task": "myapp.tasks.report"}}
        with self.assertRaises(UnknownTaskError):
            check_tasks(app)

    def test_no_schedule(self) -> None:
        """
        Test that an app without a beat schedule passes.
        """
        check_tasks(_app())
