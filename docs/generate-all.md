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
tools/generate_all.sh --out <dir> --start <ISO8601 instant> --duration <ISO8601 duration> [--profile <name>]... [--template <name>]... [--partition <duration>] [--seed <n>] [--no-schedule] [--dry-run]
```

| Option | Description |
| --- | --- |
| `--out <dir>` | Output root. Each pair is written to `<dir>/<profile>/<template>/YYYY/MM/DD/`. Required. |
| `--start <instant>` | Passed straight through to every `generator.py` run's `-s`, e.g. `2026-07-01T00:00:00`. Required. |
| `--duration <duration>` | Passed straight through to every `generator.py` run's `-r`, e.g. `P31D` or `P1M`. Required. |
| `--profile <name>` | Only this profile; repeatable. Default: all of them. Run `--help` for the current list. |
| `--template <name>` | Only this template, within whichever profiles are selected; repeatable. Default: every template a selected profile has. |
| `--partition <duration>` | ISO 8601 partition size, passed to `-p`. Default: `P1D`. |
| `--seed <n>` | Passed to every `generator.py` run as `--seed`. |
| `--no-schedule` | Skip each profile's schedule file, if it has one. |
| `--dry-run` | Print the plan — every (profile, template) pair, its output path, and the exact `generator.py` command — without running anything. |

`--start` and `--duration` are a deliberate pass-through of `generator.py`'s own `-s`/`-r` rather than a second date-range convention layered on top — whatever either flag accepts, this script accepts too, with no date arithmetic in between.

```bash
# See the plan first — no generation, just the resolved commands
tools/generate_all.sh --out out/lake --start 2026-07-01T00:00:00 --duration P31D --profile vpc_flow_logs --dry-run

# Run it
tools/generate_all.sh --out out/lake --start 2026-07-01T00:00:00 --duration P31D --profile vpc_flow_logs

# Re-run just one template within a profile — e.g. to regenerate a single
# template's output without redoing every other template for that profile too
tools/generate_all.sh --out out/lake --start 2026-07-01T00:00:00 --duration P31D --profile vpc_flow_logs --template ocsf:network_activity
```

## The profile table

The (profile, template, `-w` ceiling, schedule, extension) table this script runs is hardcoded in the script itself, not discovered from `presets/configs/*.json` at runtime. A `-w` ceiling needs a human to have actually run `tools/bench_config_workers.py` first — see [how-to-build-a-config.md](./how-to-build-a-config.md#step-10--find-the--w-ceiling-and-document-it) — so a newly-added preset shouldn't silently appear in a bulk export with a guessed concurrency value.

Adding a new preset config means adding a line to both tables near the top of the script: one entry in `PROFILES` (profile name, config file, `-w` ceiling, schedule file or `-`, `-i` override or `-`), and a `template=extension` block in `templates_for()` for each of its templates. This is also called out as the last step of the config-authoring guide — see [how-to-build-a-config.md, Step 11](./how-to-build-a-config.md#step-11--register-it-for-bulk-export).

The `-i` column defaults to `-` (the config's own interarrival rate) for every profile. It's only worth setting when a profile's default volume genuinely isn't enough — `-w` alone can't raise throughput past the natural ceiling for whatever interarrival rate is already in effect (Little's Law: `L = λW`), so deliberately raising volume means lowering `-i` *and* raising `-w` to match the new, higher ceiling, using values actually measured in that preset's own `docs/presets/<profile>.md` grid rather than guessed. `zscaler_web`'s `-i 0.1`/`-w 250` (~15× its default volume) is the current example.

The ecommerce presets (`ecommerce`, `ecommerce_lighting`, `ecommerce_furniture`) each get their own separate template block in the script, even though the three currently list identical templates — they're independent configs (see the project's own guidance on this), so keeping their entries independent here too means editing one's templates never silently affects another's.

## See also

- [split-stream.md](./split-stream.md) — the splitting mechanism this script wraps, including how to sync the result to S3
- [generator-config.md](./generator-config.md) — `-p`/`--partition`
- [how-to-build-a-config.md](./how-to-build-a-config.md) — registering a new preset here as part of building it
