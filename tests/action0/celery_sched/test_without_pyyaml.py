import subprocess
import sys
import textwrap
import unittest

# run in a fresh interpreter, because this one has imported PyYAML already
SCRIPT = textwrap.dedent(
    """\
    import io
    import sys

    sys.modules["yaml"] = None  # any "import yaml" now fails, as without PyYAML

    import action0.celery_sched as sched

    assert "action0.celery_sched.yaml_loader" not in sys.modules, "imported eagerly"
    toml = io.StringIO('[Poll]\\ntask = "myapp.tasks.poll"\\nschedule = { every = "5m" }')
    assert list(sched.load_beat_schedule(toml, format="toml")) == ["Poll"]
    mapping = {"Poll": {"task": "myapp.tasks.poll", "schedule": {"every": "5m"}}}
    assert list(sched.load_beat_schedule(mapping)) == ["Poll"]
    try:
        sched.load_beat_schedule("does-not-exist.yaml")
    except ImportError as error:
        print(error)
    """
)


class WithoutPyYamlTestCase(unittest.TestCase):
    """
    tests that the package works without PyYAML (the ``yaml`` extra)
    """

    def test_toml_and_mappings_work(self) -> None:
        """
        Test that nothing imports PyYAML until a YAML source is read, and that it then asks for the extra.
        """
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        # the YAML file is refused before it is opened, so no FileNotFoundError
        self.assertEqual(
            result.stdout.strip(),
            "YAML schedules need PyYAML: pip install 'action0-celery-sched[yaml]'",
        )
