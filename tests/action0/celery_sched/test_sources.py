import io
import tempfile
import unittest
from pathlib import Path

from action0.celery_sched.errors import DefinitionError
from action0.celery_sched.sources import read_source

TOML = '[Poll]\ntask = "myapp.tasks.poll"\n'
DOCUMENT = {"Poll": {"task": "myapp.tasks.poll"}}


class ReadSourceTestCase(unittest.TestCase):
    """
    tests for :py:func:`~action0.celery_sched.sources.read_source`
    """

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "beat.toml"
        self.path.write_text(TOML, encoding="utf-8")

    def test_mapping(self) -> None:
        """
        Test that a mapping is taken as the parsed document, unnamed and unchanged.
        """
        self.assertEqual(read_source(DOCUMENT), (None, DOCUMENT))
        # the format is about text, so it doesn't apply
        self.assertEqual(read_source(DOCUMENT, "yaml"), (None, DOCUMENT))

    def test_path(self) -> None:
        """
        Test that a path is read in the format of its suffix and named by itself.
        """
        self.assertEqual(read_source(self.path), (str(self.path), DOCUMENT))
        self.assertEqual(read_source(str(self.path)), (str(self.path), DOCUMENT))

    def test_open_files(self) -> None:
        """
        Test that files opened in text or binary mode are named and read alike.
        """
        for mode in ("r", "rb"):
            with self.subTest(mode=mode):
                with open(self.path, mode) as stream:
                    self.assertEqual(read_source(stream), (str(self.path), DOCUMENT))

    def test_unnamed_streams(self) -> None:
        """
        Test that unnamed text and binary streams are read with an explicit format.
        """
        self.assertEqual(read_source(io.StringIO(TOML), "toml"), (None, DOCUMENT))
        self.assertEqual(read_source(io.BytesIO(TOML.encode()), "toml"), (None, DOCUMENT))
        with self.assertRaisesRegex(ValueError, "unnamed stream"):
            read_source(io.StringIO(TOML))

    def test_errors_are_located(self) -> None:
        """
        Test that parse errors carry the source name.
        """
        self.path.write_text("[Poll\n", encoding="utf-8")
        with self.assertRaises(DefinitionError) as caught:
            read_source(self.path)
        self.assertEqual(caught.exception.source, str(self.path))
