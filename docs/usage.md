# Usage

## A first schedule

A schedule file is a mapping of entry names to entries. Each entry names the
task to send and when to send it. Write it in YAML:

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

Or in TOML: the same entries, with the same keys and values:

```toml
# beat.toml
["Poll feed"]
task = "myapp.feeds.tasks.poll"
schedule = { every = "5m" }

["Nightly report"]
task = "myapp.reports.tasks.nightly"
params = ["daily"]
schedule = { crontab = "0 3 * * *" }
options = { queue = "reports" }

["Nightly report".kw]
recipients = ["ops@example.com"]
```

{py:func}`~action0.celery_sched.loader.load_beat_schedule` reads either
into exactly what Celery's `beat_schedule` setting expects:

```python
from celery import Celery
from action0.celery_sched import load_beat_schedule

app = Celery("myapp")
app.conf.beat_schedule = load_beat_schedule("beat.yaml")  # or "beat.toml"
# {'Poll feed': {'task': 'myapp.feeds.tasks.poll',
#                'schedule': <freq: 5.00 minutes>,
#                'args': (),
#                'kwargs': {},
#                'options': {}},
#  'Nightly report': {'task': 'myapp.reports.tasks.nightly',
#                     'schedule': <crontab: 0 3 * * * (m/h/dM/MY/d)>,
#                     'args': ('daily',),
#                     'kwargs': {'recipients': ['ops@example.com']},
#                     'options': {'queue': 'reports'}}}
```

Load it wherever the app is configured, so that it is in place before beat
starts.

The rest of this guide shows YAML. Every example translates one-to-one to
TOML; [YAML and TOML](#yaml-and-toml) lists the few places where the formats
differ.

## YAML and TOML

The loaders take a path (a `str` or any path-like), an open stream, or a
mapping, and tell the format of a file by its suffix: `.yaml` and `.yml` are
YAML, `.toml` is TOML. Streams are judged by their name. Files opened with
`open()` have one, in text mode or binary mode (the mode `tomllib` users are
used to). For anything else, say which format it is:

```python
load_beat_schedule("conf/beat.conf", format="toml")  # or Format.TOML
load_beat_schedule(io.StringIO(text), format="yaml")
```

Without a known suffix and without `format=`, loading refuses to guess:

```text
ValueError: cannot tell the format of 'beat.conf' (known suffixes: .yaml, .yml, .toml): pass format='yaml' or format='toml'
```

TOML is read with the standard library's `tomllib`, so it needs nothing
beyond Python 3.11.

### Differences between the formats

The entries are the same. The formats themselves differ in a few places:

- **Environment variables.** TOML has no tags, so YAML's `!ENV ${VAR}` tag
  becomes a prefix inside the string: `"!ENV ${VAR}"`. See
  [Environment variables](#environment-variables).
- **Anchors and templates** are YAML only. TOML has no way to refer to another
  table, so shared settings have to be repeated there. See
  [Templates and anchors](#templates-and-anchors).
- **Duplicate names.** TOML forbids declaring a key twice, so a duplicated
  entry is already a syntax error (see [Errors](#errors)).
- **Empty values.** YAML's `kw:` with nothing after it means no keyword
  arguments. TOML has no null: leave the key out.
- **Long entries.** Inline tables (`kw = { ... }`) must fit on one line. Use a
  sub-table for longer ones, as `["Nightly report".kw]` does above.
- **Strings are quoted** in TOML: `every = "5m"`, `crontab = "0 3 * * *"`.
  Numbers and booleans are not: `every = 300`, `enabled = false`.

### Mappings

A mapping is taken as the already parsed schedule. That way, a schedule can
live inside a larger configuration file, as one table among others:

```toml
# settings.toml
[database]
url = "postgres://db/myapp"

[beat."Poll feed"]
task = "myapp.feeds.tasks.poll"
schedule = { every = "5m" }
```

```python
import tomllib

with open("settings.toml", "rb") as f:
    settings = tomllib.load(f)
app.conf.beat_schedule = load_beat_schedule(settings["beat"])
```

The same works for a dict from JSON, or from whatever settings system the app
uses. The mapping is validated exactly like a file. Only `!ENV` doesn't apply,
because the data is parsed already, and error messages can't name a file.

## Entries

| Key        | Required | Meaning                                                              |
|------------|----------|----------------------------------------------------------------------|
| `task`     | yes      | the name the task is registered under, usually its dotted path       |
| `schedule` | yes      | when to run it — see [Schedules](#schedules)                          |
| `params`   | no       | a list of positional arguments                                       |
| `kw`       | no       | a mapping of keyword arguments                                       |
| `options`  | no       | a mapping passed on to `apply_async()`: `queue`, `priority`, `expires`, ... |
| `enabled`  | no       | `false` keeps the entry in the file but out of the schedule          |

The entry's name — the key in the file — becomes its name in `beat_schedule`,
so it must be unique; quote it if it contains spaces or punctuation.

Any other key is an error. That is deliberate: a misspelled key would otherwise
be ignored, and the task would quietly never run.

```text
beat.yaml: entry 'Nightly report': unknown key 'shedule' (allowed: enabled, kw, options, params, schedule, task)
```

`params:`, `kw:` and `options:` may be left empty (`kw:` with nothing after
it), which means none.

## Schedules

The `schedule:` block is a mapping with exactly one key naming its kind:
`every`, `crontab` or `solar`.

### Intervals: `every`

```yaml
schedule:
  every: 5m
```

The interval can be written in three ways:

| YAML                             | TOML                                 | Meaning                            |
|----------------------------------|--------------------------------------|------------------------------------|
| `every: 30`                      | `every = 30`                         | seconds; fractions are fine        |
| `every: 1h30m`                   | `every = "1h30m"`                    | `<amount><unit>` parts             |
| `every: {hours: 1, minutes: 30}` | `every = { hours = 1, minutes = 30 }` | {py:class}`~datetime.timedelta` arguments |

The units of the duration string are `w`, `d`, `h`, `m`, `s` and `ms`, and
parts may have spaces between them (`2d 12h`) and fractions (`1.5h`). Units are
lowercase only, so `m` is never mistaken for months. The mapping takes
`weeks`, `days`, `hours`, `minutes`, `seconds` and `milliseconds`. The interval
must be positive.

Celery's `relative` flag goes next to `every`:

```yaml
schedule:
  every: 1h
  relative: true   # rounded to the interval: runs on the hour
```

An interval becomes a {py:class}`celery.schedules.schedule`.

### Crontabs: `crontab`

```yaml
schedule:
  crontab: "30 7 * * mon-fri"   # 07:30 on workdays
```

A five-field cron string is read in the usual cron order: minute, hour, day
of month, month, day of week. The nicknames `@hourly`, `@daily` (or
`@midnight`), `@weekly`, `@monthly` and `@yearly` (or `@annually`) work too.

Alternatively, name the fields with Celery's own argument names. The fields
you leave out mean `*`:

```yaml
schedule:
  crontab: {minute: 30, hour: 7, day_of_week: mon-fri}
```

The fields are `minute`, `hour`, `day_of_week`, `day_of_month` and
`month_of_year`. Each takes what Celery takes (`*/15`, `1-5`, `mon,wed`, a
number), and in the mapping form also a list of numbers (`minute: [0, 30]`).

Celery validates every field while the file loads, so an impossible value
fails at startup, pinned to its field:

```text
beat.yaml: entry 'Nightly report': schedule.crontab.hour: invalid value '25': Invalid end range: 25 > 23.
```

A crontab runs in the app's configured `timezone`.

### Solar events: `solar`

```yaml
schedule:
  solar: {event: sunset, lat: 48.21, lon: 16.37}
```

`event` is one of `dawn_astronomical`, `dawn_nautical`, `dawn_civil`,
`sunrise`, `solar_noon`, `sunset`, `dusk_civil`, `dusk_nautical` and
`dusk_astronomical` (also available as the
{py:class}`~action0.celery_sched.solar.SolarEvent` enum); `lat` and `lon`
are the observer's position in degrees.

Celery computes the event times with `ephem`, which comes with the `solar`
extra:

```shell
pip install "action0-celery-sched[solar]"
```

## Environment variables

Values that differ between environments can come from environment variables,
with the `!ENV` tag:

```yaml
"Nightly report":
  task: myapp.reports.tasks.nightly
  schedule:
    crontab: !ENV ${REPORT_CRON:-0 3 * * *}
  options:
    queue: !ENV ${REPORT_QUEUE}
  enabled: !ENV ${REPORTS_ENABLED:-true}
```

In TOML, which has no tags, the tag becomes a prefix of the string:

```toml
["Nightly report"]
task = "myapp.reports.tasks.nightly"
schedule = { crontab = "!ENV ${REPORT_CRON:-0 3 * * *}" }
options = { queue = "!ENV ${REPORT_QUEUE}" }
enabled = "!ENV ${REPORTS_ENABLED:-true}"
```

Only strings that *start* with `!ENV` followed by whitespace are
substituted, and only values, never keys.

`${VAR}` is replaced by the variable's value, and loading fails if it is not
set. `${VAR:-fallback}` uses the fallback instead. The tag works on scalars
only, and can mix text with several variables (`!ENV ${QUEUE}-high`).

The error says where the variable is used: the entry and key in TOML, the
line in YAML. YAML reports the line because it substitutes while parsing,
before any entry exists.

```text
beat.toml: entry 'Nightly report': options.queue: environment variable 'REPORT_QUEUE' is not set (referenced via !ENV)
```

The result is always a string. It is *not* parsed as YAML again, so a value
like `0123` or `yes` cannot turn into a number or a boolean by accident. Where
a number or a boolean is expected (intervals, crontab fields, coordinates,
`relative`, `enabled`), the string spelling is accepted. For booleans that
means `true`/`false`, `yes`/`no`, `on`/`off` and `1`/`0`. Values of `params`,
`kw` and `options` stay strings, because nothing says what type they should
be.

## Disabling entries

```yaml
"Nightly report":
  task: myapp.reports.tasks.nightly
  schedule:
    crontab: "0 3 * * *"
  enabled: false
```

A disabled entry is still validated, but left out of the beat schedule.
Combined with `!ENV` (see above) it switches entries on and off per
environment.

## Templates and anchors

YAML anchors and merge keys share settings between entries. Entries whose name
starts with a `.` are *templates*: they are there to carry an anchor and are
never scheduled, so they don't need to be complete entries:

```yaml
.reports: &reports
  task: myapp.reports.tasks.build
  options: {queue: reports}

"Daily report":
  <<: *reports
  kw: {period: day}
  schedule: {crontab: "@daily"}

"Weekly report":
  <<: *reports
  kw: {period: week}
  schedule: {crontab: "@weekly"}
```

Keys merged in with `<<:` may be overridden. Apart from that, a key that
appears twice in the same mapping is an error. Plain YAML would silently keep
the last one, so copying `"Daily report"` to make the weekly one, and then
forgetting to rename it, would replace the original:

```text
beat.yaml: duplicate entry 'Daily report' on line 10 (first on line 5)
```

Arguments shared through an anchor are copied per entry, so a task that
mutates its `kw` cannot affect another entry.

TOML has no anchors, so there the settings are repeated in each entry.
`.`-prefixed tables are skipped in TOML too, but nothing can refer to them.

## Several files

Pass several sources to merge them in order. They may be of different formats,
and mappings too:

```python
app.conf.beat_schedule = load_beat_schedule("beat/common.yaml", "beat/reports.toml")
```

An entry name defined in two files is an error, naming both. With
`replace=True` the later definition wins instead and keeps the position of
the first. Use this to let an environment-specific file override or disable
entries of a shared one:

```python
files = ["beat/common.yaml", f"beat/{environment}.yaml"]
app.conf.beat_schedule = load_beat_schedule(*files, replace=True)
```

```yaml
# beat/staging.yaml
"Nightly report":
  task: myapp.reports.tasks.nightly
  schedule: {crontab: "0 3 * * *"}
  enabled: false
```

A replacement is a whole entry, not a patch of the earlier one.

## Checking task names

Beat sends tasks by name, and a misspelled `task:` goes unnoticed until the
first run is due, and then shows up only as an error on a worker.
{py:func}`~action0.celery_sched.tasks.check_tasks` compares every
scheduled name with the tasks the app has registered, and raises
{py:class}`~action0.celery_sched.errors.UnknownTaskError` listing all
unknown ones:

```python
from celery.signals import beat_init
from action0.celery_sched import check_tasks


@beat_init.connect
def check_schedule(sender, **kwargs):
    check_tasks(sender.app)
    # if nothing is registered as myapp.feeds.tasks.poll, beat stops with:
    # UnknownTaskError: unregistered tasks: 'Poll feed' -> myapp.feeds.tasks.poll
```

The app only knows the tasks whose modules were imported. Beat imports them
(through `imports`/`include` and autodiscovery) just before it sends
`beat_init`, which is why the check belongs there and not next to
`load_beat_schedule`. By default it checks the app's own `beat_schedule`, so
entries configured some other way are covered too. Pass a schedule as the
second argument to check that one instead.

## Errors

Everything this package raises on purpose derives from
{py:class}`~action0.celery_sched.errors.ScheduleError`:

- {py:class}`~action0.celery_sched.errors.DefinitionError`: a file or
  an entry is malformed, including YAML and TOML syntax errors. Its message starts
  with the location, and the pieces are also available as the attributes
  `source`, `entry`, `path` and `reason`:

  ```text
  beat.yaml: entry 'Nightly report': schedule.crontab: expected 5 fields (minute hour day-of-month month day-of-week) or a nickname like '@daily', got 4 in '0 3 * *'
  ```

- {py:class}`~action0.celery_sched.errors.DuplicateEntryError` (a
  `DefinitionError`): an entry name is used twice, in one YAML file or across
  sources. In a single TOML file it is a syntax error instead, because TOML
  itself forbids it:

  ```text
  beat.toml: invalid TOML: Cannot declare ('Daily report',) twice (at line 5, column 16)
  ```

- {py:class}`~action0.celery_sched.errors.UnknownTaskError`: raised by
  `check_tasks`, with the offenders in `missing` (entry name → task name).

A few errors are not about the schedule's content:

- a file that doesn't exist raises the usual `FileNotFoundError`;
- a file or stream whose format can't be told raises `ValueError` (see
  [YAML and TOML](#yaml-and-toml));
- a solar schedule without `ephem` installed raises an `ImportError` naming
  the extra.

## Working with entries

{py:func}`~action0.celery_sched.loader.load_entries` returns the parsed
{py:class}`~action0.celery_sched.entries.Entry` objects instead: disabled
entries included, each knowing the file it came from. This is handy for
tooling, or for a test that checks the schedule file itself:

```python
from action0.celery_sched import load_entries

entries = load_entries("beat.yaml")
print(entries[0])
# Entry(name='Poll feed', task='myapp.feeds.tasks.poll', schedule=<freq: 5.00 minutes>,
#       args=(), kwargs={}, options={}, enabled=True, source='beat.yaml')
print(entries[0].to_celery() == load_beat_schedule("beat.yaml")["Poll feed"])
# True
```

The parsers behind the file format are public as well, each taking the parsed
YAML value of its key:
{py:func}`~action0.celery_sched.entries.parse_entry`,
{py:func}`~action0.celery_sched.schedules.parse_schedule`,
{py:func}`~action0.celery_sched.durations.parse_duration`,
{py:func}`~action0.celery_sched.crontabs.parse_crontab` and
{py:func}`~action0.celery_sched.solar.parse_solar`.

```python
from action0.celery_sched import parse_duration, parse_schedule

parse_duration("1h30m")  # datetime.timedelta(seconds=5400)
parse_schedule({"crontab": "@daily"})  # <crontab: 0 0 * * * (m/h/dM/MY/d)>
```

## Trust

YAML files are parsed with a *safe* loader and TOML files with `tomllib`, so
neither can construct arbitrary Python objects. They can, however, schedule any registered task
with any arguments, so load only files you would trust with that.
