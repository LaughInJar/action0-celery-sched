# Action0-Celery-Sched

[![CI](https://github.com/LaughInJar/action0-celery-sched/actions/workflows/ci.yml/badge.svg)](https://github.com/LaughInJar/action0-celery-sched/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/action0-celery-sched)](https://pypi.org/project/action0-celery-sched/)

Celery beat schedules defined in YAML or TOML files: which task runs when,
with which arguments, kept out of the code and validated when the app starts.

Requires Python 3.11 or newer and Celery 5.3 or newer.

Full documentation including the API reference:
<https://laughinjar.github.io/action0-celery-sched/>

**Status:** early. The file format in YAML and TOML, all three kinds of Celery
schedule, the validation and the task check work and are covered by tests; the
API may still move.

## Installation

```shell
pip install action0-celery-sched           # or: uv add action0-celery-sched
pip install "action0-celery-sched[solar]"  # with solar schedules (ephem)
```

## Usage

Write the schedule down, in YAML:

```yaml
"Poll feed":
  task: myapp.feeds.tasks.poll
  schedule:
    every: 5m                  # or 300, 90s, 1h30m, {minutes: 5}

"Nightly report":
  task: myapp.reports.tasks.nightly
  kw:                          # keyword arguments
    recipients: [ops@example.com]
  params:                      # positional arguments
    - daily
  schedule:
    crontab: "0 3 * * *"       # or {minute: 0, hour: 3}, or @daily
  options:                     # passed on to apply_async()
    queue: reports

"Sunset lights":
  task: myapp.home.tasks.lights_on
  schedule:
    solar: {event: sunset, lat: 48.21, lon: 16.37}
```

Or in TOML, with the very same entries:

```toml
["Poll feed"]
task = "myapp.feeds.tasks.poll"
schedule = { every = "5m" }

["Nightly report"]
task = "myapp.reports.tasks.nightly"
kw = { recipients = ["ops@example.com"] }
params = ["daily"]
schedule = { crontab = "0 3 * * *" }
options = { queue = "reports" }

["Sunset lights"]
task = "myapp.home.tasks.lights_on"
schedule = { solar = { event = "sunset", lat = 48.21, lon = 16.37 } }
```

And hand it to Celery:

```python
from celery import Celery
from action0.celery_sched import load_beat_schedule

app = Celery("myapp")
app.conf.beat_schedule = load_beat_schedule("beat.yaml")  # or "beat.toml"
```

The suffix decides the format (`format="toml"` for anything else). A mapping
works too, e.g. the `[beat]` table of a larger TOML config:
`load_beat_schedule(settings["beat"])`.

The result is plain Celery, a `beat_schedule` dict of `schedule`, `crontab`
and `solar` objects:

```python
{'Poll feed': {'task': 'myapp.feeds.tasks.poll',
               'schedule': <freq: 5.00 minutes>,
               'args': (),
               'kwargs': {},
               'options': {}},
 ...}
```

Everything is validated while loading. An unknown key such as a misspelled
`shedule:`, an impossible crontab field, or an entry name used twice is an
error naming the file, the entry and the key:

```text
beat.yaml: entry 'Nightly report': schedule.crontab.hour: invalid value '25': Invalid end range: 25 > 23.
```

Values that differ per environment can come from environment variables, and
entries can be switched off without deleting them:

```yaml
"Nightly report":
  task: myapp.reports.tasks.nightly
  schedule:
    crontab: !ENV ${REPORT_CRON:-0 3 * * *}
  enabled: !ENV ${REPORTS_ENABLED:-true}
```

TOML has no tags, so there `!ENV` is a prefix of the string:
`crontab = "!ENV ${REPORT_CRON:-0 3 * * *}"`.

Several files merge in order, whatever their format. With `replace=True` a
later file may override or disable entries of an earlier one:

```python
app.conf.beat_schedule = load_beat_schedule(
    "beat/common.yaml", f"beat/{environment}.toml", replace=True
)
```

A misspelled `task:` name would only surface when the task is first due. Catch
it when beat starts instead:

```python
from celery.signals import beat_init
from action0.celery_sched import check_tasks


@beat_init.connect
def check_schedule(sender, **kwargs):
    check_tasks(sender.app)  # raises UnknownTaskError listing every unknown name
```

See the [usage guide](https://laughinjar.github.io/action0-celery-sched/usage.html)
for the full file format: every interval and crontab spelling, `relative`
intervals, how YAML and TOML differ, templates and anchors, and the error
types.

The `action0` namespace is simply the one the author likes to use for
personal projects.

## Development

```shell
uv run pytest          # tests (incl. doctests in src/)
uv run ruff check      # lint
uv run ruff format     # format
uv run mypy            # type-check (strict)
uv run pyright         # type-check
uv run ty check        # type-check
```

## AI disclosure

This library is developed with heavy use of AI coding tools: the code,
tests, and documentation are largely written by
[Claude Code](https://claude.com/claude-code), working from the author's
design brief and reviewed by the author. If that changes how much you want
to rely on this package, that's a fair call — read the source, it's small.

## License

MIT — see [LICENSE](LICENSE).
