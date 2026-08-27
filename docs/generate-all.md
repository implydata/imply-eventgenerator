# Generating the full preset catalog

`tools/generate_all.sh` runs [`tools/split_stream.sh`](./split-stream.md) in series for every (profile, template) pair in its own table — one continuous `generator.py` run per pair, covering the whole date range in a single pass, split straight into a local directory tree.

Reach for it when you want a straightforward, sequential build across some or all of the preset catalog into a local directory — one command instead of running `split_stream.sh` by hand for each config. See [split-stream.md](./split-stream.md#copying-to-s3) for uploading what it produces to S3 with `aws s3 sync`.

## Requirements

GNU `csplit`, same as `split_stream.sh` — see [its requirements section](./split-stream.md#requirements).

## Sleep protection

This script re-execs itself under `caffeinate -i` automatically on macOS, so idle sleep can't interrupt what's often a multi-hour run. This isn't just tidiness — it's a real, observed failure mode: the engine's threads coordinate via an untimed `threading.Event.wait()`, and a sleep/wake cycle mid-run can lose that wakeup permanently. The process doesn't crash or recover once the machine wakes back up — it just sits there indefinitely, with no further progress and no error, even if the machine then stays awake for hours afterward.

`caffeinate -i` only prevents *idle* sleep — closing the lid sleeps the machine regardless of any assertion, so leave it open (or run plugged in with the lid open) for the duration of a long generation run. An INFO line is printed at startup confirming this is active. If `caffeinate` isn't found (non-macOS), a warning is printed and the run proceeds without this protection — on those platforms, make sure your own power/sleep settings won't interrupt a long run.

Running [`split_stream.sh`](./split-stream.md) directly, rather than through this script, doesn't get this protection — it's worth keeping the machine awake yourself for the duration if you're driving a long run that way.

## Usage

```text
tools/generate_all.sh --out <dir> --start <ISO8601 instant> --duration <ISO8601 duration> --volume <name> [--profile <name>]... [--template <name>]... [--partition <duration>] [--seed <n>] [--no-schedule] [--dry-run]
```

| Option | Description |
| --- | --- |
| `--out <dir>` | Output root. Each pair is written to `<dir>/<profile>/<template>/<volume>/YYYY/MM/DD/`. Required. |
| `--start <instant>` | Passed straight through to every `generator.py` run's `-s`, e.g. `2026-07-01T00:00:00`. Required. |
| `--duration <duration>` | Passed straight through to every `generator.py` run's `-r`, e.g. `P31D` or `P1M`. Required. |
| `--volume <name>` | Target output volume: overrides the profile's own `-i`/`-w` with the settings recorded for it in `tools/generate_all.json`, and becomes a path segment in the output directory. Required. A profile with no entry for the requested volume is skipped, not an error — see [The config file](#the-config-file). |
| `--profile <name>` | Only this profile; repeatable. Default: all of them. Run `--help` for the current list. |
| `--template <name>` | Only this template, within whichever profiles are selected; repeatable. Default: every template a selected profile has. |
| `--partition <duration>` | ISO 8601 partition size, passed to `-p`. Default: `P1D`. |
| `--seed <n>` | Passed to every `generator.py` run as `--seed`. |
| `--no-schedule` | Skip each profile's schedule file, if it has one. |
| `--dry-run` | Print the plan — every (profile, template) pair, its output path, and the exact `generator.py` command — without running anything. |

`--start` and `--duration` are a deliberate pass-through of `generator.py`'s own `-s`/`-r` rather than a second date-range convention layered on top — whatever either flag accepts, this script accepts too, with no date arithmetic in between.

```bash
# See the plan first — no generation, just the resolved commands
tools/generate_all.sh --out out/lake --start 2026-07-01T00:00:00 --duration P31D --volume tiny --profile vpc_flow_logs --dry-run

# Run it
tools/generate_all.sh --out out/lake --start 2026-07-01T00:00:00 --duration P31D --volume tiny --profile vpc_flow_logs

# Re-run just one template within a profile — e.g. to regenerate a single
# template's output without redoing every other template for that profile too
tools/generate_all.sh --out out/lake --start 2026-07-01T00:00:00 --duration P31D --volume tiny --profile vpc_flow_logs --template ocsf:network_activity
```

## The config file

`tools/generate_all.json` is the single source of truth for everything this script runs — nothing is discovered from `presets/configs/*.json` at runtime, and the script itself carries no per-profile data. For each profile it records:

- `config` — the config file (relative to `presets/configs/`)
- `schedule` — the schedule file (relative to `presets/schedules/`), or `null` if the profile has none
- `templates` — a list of `{"name": ..., "ext": ...}` pairs, one per template the profile supports
- `volumes` — `-i`/`-w` settings per named volume (see below)

Adding a new preset config means adding its entry to `tools/generate_all.json`, not editing the script. This is also called out as the last step of the config-authoring guide — see [how-to-build-a-config.md, Step 11](./how-to-build-a-config.md#step-11--register-it-for-bulk-export). A `-w` ceiling needs a human to have actually run `tools/bench_config_workers.py` first — see [how-to-build-a-config.md](./how-to-build-a-config.md#step-10--find-the--w-ceiling-and-document-it) — so a newly-added preset shouldn't silently appear in a bulk export with a guessed concurrency value.

The ecommerce presets (`ecommerce`, `ecommerce_lighting`, `ecommerce_furniture`) each get their own separate `templates` list, even though the three currently list identical templates — they're independent configs (see the project's own guidance on this), so keeping their entries independent here too means editing one's templates never silently affects another's.

### Volumes

The top-level `volumes` object maps a small set of named output sizes (`tiny`, `x-small`, `small`, `medium`, `large`, `x-large`, `huge`) to target row-count caps. `--volume <name>` is required on every run: it looks up that profile's `-i`/`-w` entry under its `volumes` key and uses it in place of any other default, and the volume name also becomes a path segment in the output directory (`<profile>/<template>/<volume>/...`), so runs at different volumes never collide on disk.

Each named volume is a **cap**, not a target average — the settings for a given profile/volume pair are tuned so that no single day's row count exceeds it, not just so the mean lands near it. This matters because per-day output isn't uniform: a profile with a schedule (the ecommerce family) has a real weekly business-hours cycle, so its peak day can run well above its own weekly average — tuning to the mean alone would let peak days overshoot the cap. Each entry's `-i`/`-w` is validated against the *observed maximum*, not the mean, over a multi-day test window where practical — `-w` alone can't raise throughput past the natural ceiling for whatever interarrival rate is already in effect (Little's Law: `L = λW`), so raising volume means lowering `-i` *and* raising `-w` to match the new, higher ceiling, using values actually measured rather than guessed.

Not every profile supports every volume — the ceiling a profile can actually reach depends on its own `-w`/`-i` limits (see each preset's own `docs/presets/<profile>.md` Volume section). A profile with no recorded entry for the requested volume is skipped with a message rather than failing the whole run, so `--volume large --profile ecommerce --profile endpoint_network` runs whichever of the two actually supports `large` and says why it skipped the other.

Each entry also records `observed_max_rows_per_day`, `observed_mean_rows_per_day`, `test_window_days`, and `tested_on` — real, measured values from an actual run, not an extrapolation — so the file doubles as a record of what's actually been verified for that profile/volume pair, and of how much headroom exists below the cap. A `test_window_days` of 1 means only a single day was measured (typically because a longer run was too expensive to justify for that profile's volume) — treat its margin below the cap as less battle-tested than an entry backed by a multi-day sweep.

## See also

- [split-stream.md](./split-stream.md) — the splitting mechanism this script wraps, including how to sync the result to S3
- [generator-config.md](./generator-config.md) — `-p`/`--partition`
- [how-to-build-a-config.md](./how-to-build-a-config.md) — registering a new preset here as part of building it
