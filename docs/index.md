# action0-celery-sched

Celery beat schedules defined in YAML or TOML files: which task runs when, with
which arguments, kept out of the code and validated when the app starts.

```shell
# not on PyPI yet — install from GitHub for now
uv add action0-celery-sched            # TOML schedules
uv add "action0-celery-sched[yaml]"    # YAML schedules too (PyYAML)
```

Write the schedule down, in either format:

::::{tab-set}
:sync-group: format

:::{tab-item} YAML
:sync: yaml

```yaml
# beat.yaml
"Poll feed":
  task: myapp.feeds.tasks.poll
  schedule:
    every: 5m

"Nightly report":
  task: myapp.reports.tasks.nightly
  kw:
    recipients: [ops@example.com]
  params:
    - daily
  schedule:
    crontab: "0 3 * * *"
  options:
    queue: reports
```

And hand it to Celery:

```python
from celery import Celery
from action0.celery_sched import load_beat_schedule

app = Celery("myapp")
app.conf.beat_schedule = load_beat_schedule("beat.yaml")
```
:::

:::{tab-item} TOML
:sync: toml

```toml
# beat.toml
["Poll feed"]
task = "myapp.feeds.tasks.poll"
schedule = { every = "5m" }

["Nightly report"]
task = "myapp.reports.tasks.nightly"
kw = { recipients = ["ops@example.com"] }
params = ["daily"]
schedule = { crontab = "0 3 * * *" }
options = { queue = "reports" }
```

And hand it to Celery:

```python
from celery import Celery
from action0.celery_sched import load_beat_schedule

app = Celery("myapp")
app.conf.beat_schedule = load_beat_schedule("beat.toml")
```
:::
::::

**Highlights**:

- YAML and TOML on equal footing: the same entries, keys and values in both,
  or an already parsed mapping, such as a table of a larger config file. TOML
  needs nothing but the standard library's `tomllib`, YAML the `yaml` extra.
- Every kind of schedule Celery has: intervals (`90s`, `1h30m`, a number of
  seconds or `timedelta` arguments), crontabs (`"30 7 * * mon-fri"`, `@daily`,
  or a mapping of fields) and solar events (sunset at a latitude and
  longitude).
- Strict validation at load time: unknown keys (a misspelled `shedule`),
  impossible crontab fields and duplicate entry names are errors that say
  which file, entry and key they are in — not a silently missing schedule.
- `!ENV ${VAR:-fallback}` for values that differ per environment, and
  `enabled` set to false to keep an entry but not run it.
- Several files merged in order, formats mixed, optionally letting a later
  one override entries of an earlier one.
- {py:func}`~action0.celery_sched.tasks.check_tasks` to verify, at beat
  startup, that every scheduled task name is actually registered.
- The output is plain Celery: a `beat_schedule` dict of
  {py:class}`celery.schedules.schedule`, {py:class}`~celery.schedules.crontab`
  and {py:class}`~celery.schedules.solar` objects.
- Fully typed (checked with mypy strict, pyright and ty), Python 3.11+.

The `action0` namespace is simply the one the author likes to use for personal
projects.

```{toctree}
:maxdepth: 2

usage
api
```
