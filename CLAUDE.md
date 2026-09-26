# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`action0-celery-sched` is a Python library that reads Celery beat schedules from YAML or TOML files (or already-parsed mappings) and turns them into the value of Celery's `beat_schedule` setting (`app.conf.beat_schedule = load_beat_schedule("beat.yaml")`). It ships the `action0.celery_sched` package (`action0` is a PEP 420 namespace package) from a `src/` layout, is built with hatchling, and uses `uv` for environment/dependency management. The only runtime dependency is `celery`: TOML uses the stdlib `tomllib`, YAML needs the optional `yaml` extra (PyYAML), and the optional `solar` extra adds `ephem`, which Celery needs to build `solar` schedules. Importing the package must never import PyYAML — `test_without_pyyaml.py` guards that.

## Rules

- **Never commit without asking.** Also never push, tag, or publish on your own.
- **Branches + PRs.** All changes go through feature branches and GitHub pull requests that Simon reviews and merges — never commit to `main` directly. (Only the initial implementation is built directly on `main`; once that phase is over, this applies without exception.)
- **Discuss first.** Always present the plan and the intended edits and get agreement before changing files.
- Every code change comes with: tests, docstrings, inline comments where the code isn't self-explanatory, and updated usage examples in `README.md` and the Sphinx docs (`docs/usage.md`).
- Before considering work done, run ruff, mypy, pyright, ty and pytest (commands below) and fix what they report.
- Supported Python versions: 3.11 up to the latest release. Don't use syntax or stdlib features introduced after 3.11 (no PEP 695 `type` aliases or generics — use `TypeAlias`), and don't rely on behavior removed in newer versions.
- Prefer many small modules and short functions over large ones.

## Commands

`uv run` syncs the environment automatically (the dev dependency group is installed by default), so no separate install step is needed.

```sh
uv run pytest                                               # all tests
uv run pytest tests/action0/celery_sched/test_loader.py  # one file
uv run pytest tests/action0/celery_sched/test_loader.py::MergeTestCase::test_replace  # one test

uv run ruff check      # lint (add --fix to autofix)
uv run ruff format     # format
uv run mypy            # type-check (strict; files are configured in pyproject.toml)
uv run pyright         # type-check
uv run ty check        # type-check

uv run --group docs sphinx-build -W --keep-going -b html docs docs/_build/html  # build docs

uv build               # build sdist + wheel into dist/
```

`pytest` also runs the `>>>` examples in the docstrings as doctests (`--doctest-modules` over `src/`), so docstring examples must produce their shown output exactly.

## Architecture

The file format is the same in YAML and TOML — Simon's requirement: an entry is identical regardless of format. A top-level mapping of entry name → entry; entry keys `task` (required), `schedule` (required), `params` (positional args), `kw` (keyword args), `options` (passed to `apply_async`), `enabled`. The `schedule` has exactly one of `every` / `crontab` / `solar` (plus `relative`, only next to `every`). The names `kw`/`params` are the user-facing names chosen by Simon; they map to Celery's `kwargs`/`args`.

Data flow: source (path / stream / mapping) → `sources.read_source` → `formats.detect_format` + `formats.parse_text` → `yaml_loader.load_yaml` or `toml_loader.load_toml` → plain Python data → `loader._parse_document` → `entries.parse_entry` (and below it the format-agnostic parsers) → `Entry` → `to_celery()`. Everything from `_parse_document` down never knows which format the data came from; keep it that way.

Modules under `src/action0/celery_sched/`, one concern each, from the leaves up:

- `errors.py` — `ScheduleError` base; `DefinitionError` carries `reason` plus a location (`source` file, `entry` name, key `path`) rendered as `beat.yaml: entry 'X': schedule.crontab.hour: reason`; `DuplicateEntryError`; `UnknownTaskError` (with `missing`). `located(*keys, entry=, source=)` is the context manager that fills the location in on the way up — parsers only ever raise with a reason and wrap each descent in `with located("key"):`.
- `values.py` — shared validators: `expect_mapping`, `check_keys` (unknown keys are errors — the typo guard), `as_number`, `as_bool`, `describe`. Number/boolean validators accept string spellings because `!ENV` always yields strings.
- `durations.py` — `parse_duration`: seconds (number or numeric string), duration strings (`1h30m`, units `w d h m s ms`, lowercase only), or a `timedelta`-kwargs mapping; must be positive and finite.
- `crontabs.py` — `parse_crontab`: five-field cron string (cron order; own whitespace split because Celery's `crontab.from_string` splits on single spaces only), `@daily`-style nicknames, or a mapping of Celery's field names. Each field is validated by constructing a one-field `crontab` so the error is pinned to its key.
- `solar.py` — `SolarEvent` (StrEnum of Celery's events) and `parse_solar`; range checks happen before construction, and a missing `ephem` becomes an `ImportError` naming the `solar` extra.
- `schedules.py` — `parse_schedule` dispatches on the one kind key. Intervals become `celery.schedules.schedule(timedelta, relative=...)` objects, so every kind comes out as a `BaseSchedule` that beat takes as-is.
- `entries.py` — `Entry` (frozen dataclass; `source` excluded from equality), `BeatEntry` (TypedDict of one `beat_schedule` value), `parse_entry`. Argument containers are deep-copied so YAML-anchor-shared mappings are never shared at runtime.
- `envvars.py` — `substitute_env` for `${VAR}` / `${VAR:-fallback}`; textual, never re-parsed (same semantics as action0-service's `!ENV`).
- `yaml_loader.py` — `load_yaml` (wraps `yaml.YAMLError` into `DefinitionError`) and `ScheduleLoader`, a `SafeLoader` with the `!ENV` tag (unset variables are reported with their line — entry/key aren't known while parsing) and duplicate-key detection. Duplicates are checked in `flatten_mapping` (the one hook that sees a mapping's own pairs before merge keys are spliced in), once per node — a node can be flattened again as a merge source after it was rewritten, which would otherwise produce false duplicates (there are tests for exactly that). A duplicate at the root is a `DuplicateEntryError`.
- `toml_loader.py` — `load_toml`: `tomllib.loads` (syntax errors, which include TOML's own duplicate-key errors, become `DefinitionError`), then a walk substituting strings that start with `!ENV` + whitespace — TOML has no tags, so the tag is spelled as a string prefix (precedent: dynaconf's `"@int ..."`). The walk runs under `located()`, so unset variables report entry and key path. Keys are never substituted.
- `formats.py` — `Format` (StrEnum YAML/TOML), `FormatLike` (`Format | Literal[...]`, like action0-pipeline's `ErrorPolicyLike`), `SUFFIXES`, `detect_format` (explicit `format` wins, else suffix — case-insensitive `.yaml`/`.yml`/`.toml`; anything else raises `ValueError`, deliberately no default), `parser_for` (imports `yaml_loader` lazily; an `ImportError` whose `name` is `"yaml"` becomes one naming the `yaml` extra, any other `ImportError` propagates untouched) and `parse_text` (dispatch through `parser_for`). Nothing may import `yaml_loader` at module level.
- `sources.py` — `Source` (path | `IO[str]` | `IO[bytes]` | `Mapping`) and `read_source`: mappings pass through unnamed (no `!ENV`, no format); paths and streams get their format detected and their parser obtained *before* any I/O (so an unknown format or a missing PyYAML fails without touching the file), binary streams are decoded as UTF-8 (tomllib users open files `"rb"`).
- `loader.py` — `load_entries(*sources, replace=False, format=None)` (all entries incl. disabled, merged in order across formats; cross-source duplicates raise unless `replace`, which keeps the first position) and `load_beat_schedule` (enabled entries → `to_celery()`). `_parse_document` is the format-agnostic document layer: `None` → empty, top level must be a mapping, top-level keys starting with `.` are templates (anchor carriers in YAML, merely skipped in TOML).
- `tasks.py` — `check_tasks(app, schedule=None)` compares task names with `app.tasks` (default: the app's own `beat_schedule`). Documented to run in a `beat_init` handler, because beat imports task modules right before sending that signal.

Deliberate decisions worth keeping:

- **Strict over lenient**: unknown keys, duplicate keys and invalid crontab fields fail at load time — a silently dropped schedule is the failure mode this library exists to prevent.
- **Explicit schedule kinds** (`every` / `crontab` / `solar`), no shape-inferred scalar shorthand — chosen by Simon.
- `replace=True` replaces whole entries; there is no field-level patching across files.
- Format differences that are inherent and documented, not papered over: anchors/templates are YAML-only; a duplicate entry within one TOML file is a TOML syntax error (a `DefinitionError`, not a `DuplicateEntryError` — parsing tomllib's message would be fragile); TOML has no null, so empty `kw:`-style values are simply omitted.
- `tests/action0/celery_sched/test_format_parity.py` loads one feature-complete schedule written in both formats and requires identical entries (including `schedule.relative`, which Celery's `schedule.__eq__` ignores). Any new entry feature must be added to both spellings there.

Conventions:

- The version is single-sourced as `__version__` in `src/action0/celery_sched/__init__.py`; hatch extracts it with the regex in `[tool.hatch.version]`. Bump it only there.
- Releases: pushing a `vX.Y.Z` tag triggers `.github/workflows/release.yml`, which re-runs all checks, verifies the tag matches `__version__`, builds, and publishes to PyPI via trusted publishing (environment `pypi`). Never bump the version, tag, or publish on your own — releasing is the user's call.
- Tests mirror the `src/` layout under `tests/action0/celery_sched/` and are `unittest.TestCase` classes, executed via pytest. `test_loader.py` includes an integration test that feeds the result (from both formats) into Celery's own `beat.Scheduler`.
- `test_without_pyyaml.py` runs a subprocess with `sys.modules["yaml"] = None` (stricter than uninstalling: it also catches indirect imports) and checks that the package imports, TOML and mapping sources load, and a YAML source raises the extra's `ImportError` before any I/O.
- Celery ships no type information; the dev group includes `celery-types` (stubs), `pyyaml` (the `yaml` extra, for tests and docs) and `types-pyyaml`. Where the stubs lack something (e.g. `solar._all_events`), use `getattr` with a comment rather than an ignore. When an ignore is unavoidable, silence each checker with its own syntax (`# type: ignore[code]  # ty: ignore[code]`).
- Ruff enforces one import per line (isort `force-single-line`), line length 99, `action0` as first-party. Ruff only honours `.gitignore` inside a git repository.
- Docs live in `docs/` (Sphinx + Furo, MyST Markdown pages, sphinx-design tabs, autodoc for the API reference, intersphinx to Python and Celery). Docstrings are Sphinx-reST (`:param:`, `:py:func:` roles). CI builds them with `-W` on every run and deploys to GitHub Pages on pushes to `main`. Examples in `docs/usage.md` and `README.md` show real outputs and error messages — keep them truthful, and keep every fenced `yaml`/`toml` block valid.
- **Both formats, equally (Simon's rule):** every example is given in YAML *and* TOML — in the guide, the index, the README and docstring examples. YAML comes first, TOML second. In Sphinx pages, use a sphinx-design tab-set with `:sync-group: format` and tab items `YAML` (`:sync: yaml`) then `TOML` (`:sync: toml`); a shown error message goes inside the tab next to the input that causes it. On GitHub-rendered files (README) and in docstrings, a YAML block followed by the equivalent TOML block. Each pair must mean the same (identical entries). Prose stays format-neutral: write `schedule`, not `schedule:` or `schedule =`. Only features that exist in one format alone (YAML anchors/templates) are shown in one format, next to how the other format does without.
- The GitHub Pages site must be enabled once per repo before `deploy-docs` can run: `gh api repos/LaughInJar/action0-celery-sched/pages -X POST -f build_type=workflow`.
- The README carries an AI-usage disclosure section — keep it accurate when the development workflow changes.
