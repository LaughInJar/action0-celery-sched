import os
import unittest
from unittest import mock

from action0.celery_sched.envvars import substitute_env
from action0.celery_sched.errors import DefinitionError


class SubstituteEnvTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.envvars.substitute_env`
    """

    def test_variables_and_fallbacks(self) -> None:
        """
        Test that set variables win over fallbacks, and fallbacks fill the gaps.
        """
        environ = {"HOUR": "7"}
        self.assertEqual(substitute_env("0 ${HOUR} * * *", environ), "0 7 * * *")
        self.assertEqual(substitute_env("0 ${HOUR:-3} * * *", environ), "0 7 * * *")
        self.assertEqual(substitute_env("0 ${OTHER:-3} * * *", environ), "0 3 * * *")
        self.assertEqual(substitute_env("${OTHER:-}", environ), "")

    def test_empty_variable_is_set(self) -> None:
        """
        Test that a variable set to the empty string does not fall back.
        """
        self.assertEqual(substitute_env("${EMPTY:-x}", {"EMPTY": ""}), "")

    def test_missing_variable(self) -> None:
        """
        Test that an unset variable without fallback is an error.
        """
        with self.assertRaisesRegex(DefinitionError, "'MISSING' is not set"):
            substitute_env("${MISSING}", {})

    def test_not_reparsed(self) -> None:
        """
        Test that substituted text is inserted verbatim, not substituted again.
        """
        self.assertEqual(substitute_env("${A}", {"A": "${B}", "B": "x"}), "${B}")

    def test_defaults_to_os_environ(self) -> None:
        """
        Test that the process environment is used when none is given.
        """
        with mock.patch.dict(os.environ, {"ACTION0_TEST_QUEUE": "reports"}):
            self.assertEqual(substitute_env("${ACTION0_TEST_QUEUE}"), "reports")
