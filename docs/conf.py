"""Sphinx configuration for the action0-celery-sched documentation."""

import sys
from pathlib import Path

# make the package importable even without an installed wheel
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from action0.celery_sched import __version__  # noqa: E402

project = "action0-celery-sched"
author = "Simon Lachinger"
project_copyright = "2026, Simon Lachinger"
version = __version__
release = __version__

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
    "sphinx_design",
]

# link references like :py:class:`celery.schedules.crontab` to the upstream docs
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "celery": ("https://docs.celeryq.dev/en/stable", None),
}

# order the API reference like the source files and merge the rich __init__
# docstrings into their class documentation
autodoc_member_order = "bysource"
autoclass_content = "both"

# sphinx-autodoc-typehints: document every parameter type and default value
always_document_param_types = True
typehints_defaults = "comma"

myst_enable_extensions = ["colon_fence"]
# allow links to headings, like [Schedules](#schedules)
myst_heading_anchors = 3

html_theme = "furo"
html_title = f"action0-celery-sched {__version__}"
