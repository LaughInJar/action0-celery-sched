"""
Check that every scheduled task is actually registered with the Celery app.

Beat sends tasks by *name*, and a misspelled name is not noticed until the
first run is due — possibly hours after a deploy — and then only as an
error on the worker. :py:func:`check_tasks` catches it at startup.

The app only knows the tasks whose modules were imported. Beat imports them
(``imports``/``include`` and autodiscovery) right before it sends the
``beat_init`` signal, which makes that the place to check:

.. code-block:: python

    from celery.signals import beat_init


    @beat_init.connect
    def check_schedule(sender, **kwargs):
        check_tasks(sender.app)
"""

from collections.abc import Mapping
from typing import Any

from celery import Celery

from action0.celery_sched.errors import UnknownTaskError


def check_tasks(app: Celery, schedule: Mapping[str, Mapping[str, Any]] | None = None) -> None:
    """
    Raise if a schedule entry refers to a task the app hasn't registered.

    >>> app = Celery("example")
    >>> @app.task(name="myapp.tasks.poll")
    ... def poll() -> None: ...
    >>> check_tasks(app, {"Poll feed": {"task": "myapp.tasks.poll"}})
    >>> check_tasks(app, {"Report": {"task": "myapp.tasks.report"}})
    Traceback (most recent call last):
    ...
    action0.celery_sched.errors.UnknownTaskError: unregistered tasks: 'Report' -> myapp.tasks.report

    :param app: the Celery app whose task registry to check against
    :param schedule: the entries to check, in ``beat_schedule`` shape (default:
        the app's own ``beat_schedule`` setting, so entries configured some
        other way are checked too)
    :raises UnknownTaskError: listing every entry whose task is unregistered
    """
    # the setting is untyped (Any), so give the result a declared type of its own
    entries: Mapping[str, Mapping[str, Any]] = (
        (app.conf.beat_schedule or {}) if schedule is None else schedule
    )
    registered = app.tasks
    missing = {
        name: entry["task"] for name, entry in entries.items() if entry["task"] not in registered
    }
    if missing:
        raise UnknownTaskError(missing)
