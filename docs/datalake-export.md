# Datalake export

`tools/generate_lake.py` generates bulk historical data for every preset and template and
writes it to S3 as a date-partitioned datalake:

```
s3://<bucket>/<prefix>/<profile>/<template>/<YYYY>/<MM>/<DD>/<profile>-<template>-<YYYYMMDD>.<ext>.gz
```

One object per profile, per template, per day.

## Quick start

```bash
# Plan the run — prints partitions and estimated volume, generates nothing
python tools/generate_lake.py --bucket my-lake --prefix eventgen \
  --start 2026-05-27 --end 2026-08-24 --dry-run

# Full run, 16 parallel generators
python tools/generate_lake.py --bucket my-lake --prefix eventgen \
  --start 2026-05-27 --end 2026-08-24 --jobs 16

# One profile and template to a local tree — smoke test without S3
python tools/generate_lake.py --local-dir /tmp/lake \
  --start 2026-05-27 --end 2026-05-28 --profile ecommerce --template csv
```

Re-running the same command **resumes**: partitions recorded as complete in the manifest are
skipped, so an interrupted run picks up where it stopped.

## How it works

Each partition is one `generator.py` invocation covering exactly one simulated day:

```bash
python generator.py -c presets/configs/ecommerce.json -t csv -m 2112 \
  -r P1D -s 2026-05-27T00:00:00 --schedule presets/schedules/ecommerce.json
```

Because the run's own arguments fix the day, the partition needs no timestamp parsing — which
matters when the presets emit NDJSON, CSV, NCSA combined, IIS and key-value formats that would
each need their own timestamp regex. Runs are fully independent, so they parallelise across
cores and each one either lands as a complete object or not at all.

stdout is gzipped as it streams and uploaded as a single object; nothing is staged on local
disk unless a partition exceeds 64 MB compressed, at which point it spools to a temp file.

Partition boundaries are exact: the simulated clock starts at `00:00:00` on the partition day
and `-r P1D` stops it a day later, so every record falls inside its UTC day. Verified on
`vpc_flow_logs` — 795,003 records spanning `00:00:00Z` to `23:59:58Z`, zero leakage either
side. Sessions that would have crossed midnight are cut at the boundary rather than spilling
into the next partition.

Templates with a `header` (CSV, the IIS variants) write that header once per object, which is
what a per-day file wants.

### Sub-daily objects

`--split-hours` divides each day into several objects, adding an hour marker to the filename
while keeping the same `y/m/d` folder:

```
vpc_flow_logs/aws_cloudwatchlogs_vpcflow/2026/06/20/vpc_flow_logs-...-20260620T00.log.gz
vpc_flow_logs/aws_cloudwatchlogs_vpcflow/2026/06/20/vpc_flow_logs-...-20260620T06.log.gz
```

Each window is exact — verified at `--split-hours 6`, the four objects covered `00:00:00`–
`05:59:58`, `06:00:00`–`11:59:58`, `12:00:00`–`17:59:58` and `18:00:00`–`23:59:58` UTC with no
overlap or gap.

Two reasons to use it. It shrinks the work unit, so a day of the heaviest profile parallelises
instead of occupying one core for minutes — one `vpc_flow_logs` day went from 44s at
`--split-hours 24` to 15s at `--split-hours 6` on four cores. And it caps object size, which
matters because gzip is not splittable: a full day of `vpc_flow_logs_derived` is ~76 MB in one
object that no reader can split.

The cost is boundary artifacts. Each sub-run starts with an empty worker pool that has to ramp
up, and sessions in flight are cut at every boundary — the same 6-hour split yielded 791,701
rows against 795,003 for the undivided day, 0.4% lost to three extra cut points. Keep the
default for maximum realism; reach for `--split-hours 6` or `4` on the heavy profiles.

## Options

| Argument | Description |
| --- | --- |
| `--bucket` | Destination S3 bucket. Mutually exclusive with `--local-dir`. |
| `--local-dir` | Write the same partition tree to a local directory instead of S3. |
| `--prefix` | Key prefix within the bucket. Default: bucket root. |
| `--start` / `--end` | First and last day to generate, inclusive (`YYYY-MM-DD`). |
| `--profile` | Only this profile (config basename). Repeatable. Default: every config. |
| `--exclude-profile` | Skip this profile. Repeatable. |
| `--template` | Only this template name. Repeatable. Default: every template in each config. |
| `--jobs` | Parallel generator processes. Default: cores minus 2. |
| `--split-hours` | Split each day into objects of this many hours (1, 2, 3, 4, 6, 8, 12 or 24). Default: 24 — one object per day. |
| `-m` / `--concurrency` | Override `-m` for every profile. Default: each profile's measured ceiling. |
| `--no-schedule` | Ignore per-profile schedules. Raises ecommerce volume by ~1.5×. |
| `--seed-base` | Derive each day's `--seed` as `seed-base + day ordinal`. See the caveat below. |
| `--compresslevel` | gzip level 1–9. Default: 6. |
| `--storage-class` | S3 storage class, e.g. `STANDARD_IA`. |
| `--sse` / `--kms-key-id` | Server-side encryption, e.g. `AES256` or `aws:kms` with a key id. |
| `--acl` | Object ACL, e.g. `bucket-owner-full-control`. |
| `--manifest` | JSONL run log, also used for resume. Default: `lake_manifest.jsonl`. |
| `--overwrite` | Regenerate partitions already recorded in the manifest. |
| `--check-remote` | Also skip partitions already present at the destination (one HEAD each). |
| `--task-timeout` | Kill a single partition after N seconds. Default: no limit. |
| `--dry-run` | Print the plan and exit. |

## Volume per profile

`-m` defaults to each profile's concurrency ceiling — the point past which `-m` no longer
raises throughput, so the interarrival mean sets the natural event rate. Ceilings live in
`PROFILE_SETTINGS` at the top of the tool; measure new ones with `tools/bench_config.py`.

Measured rates, with the ecommerce schedule applied to the three ecommerce profiles:

| Profile | `-m` | Schedule | rows/day | 90 days raw (all templates) |
| --- | --- | --- | --- | --- |
| `ecommerce` | 2112 | `ecommerce.json` | ~533k | ~135 GB (11 templates) |
| `ecommerce_lighting` | 2112 | `ecommerce.json` | ~700k | ~177 GB (11 templates) |
| `ecommerce_furniture` | 528 | `ecommerce.json` | ~156k | ~40 GB (11 templates) |
| `vpc_flow_logs_derived` | 1056 | — | ~7.04M | ~66 GB |
| `vpc_flow_logs` | 66 | — | ~795k | ~7 GB |
| `endpoint_network` | 1 | — | ~289k | ~2 GB |
| `ssh_auth` | 66 | — | ~21k | ~165 MB |
| `pbx_calls` | 9 | — | ~2.9k | ~48 MB |

A full 3-month run over all 8 profiles is **3,420 partitions, ~2.1 billion rows, ~425 GB raw,
~42 GB in S3** after gzip (measured 8.5–10.7:1 depending on format).

To generate less: lower `-m` (throughput scales with it below the ceiling), narrow
`--profile`/`--template`, or shorten the date range.

## Wall-clock and instance sizing

Measured per-partition cost for one simulated day, one generator, no contention:

| Profile | Solo wall per day | Rows/day | gzip/day | Ratio |
| --- | --- | --- | --- | --- |
| `vpc_flow_logs_derived` | 8m 25s | 7.04M | 85.3 MB | 8.6:1 |
| `ecommerce` (`apache:access:json`) | 43s | 563k | 20.3 MB | 13.1:1 |
| `vpc_flow_logs` | 44s | 795k | 10.3 MB | 8.5:1 |
| `ssh_auth` | 1.8s | 21k | 0.3 MB | — |
| `pbx_calls` | 0.6s | 2.9k | 0.1 MB | — |

Summed over a 3-month run of every profile and template that is roughly **44 CPU-hours**: the
three ecommerce profiles are ~68% of it (11 templates each, every one a separate pass) and
`vpc_flow_logs_derived` a further 29% on its own.

`vpc_flow_logs_derived` is worth calling out. At its `-m 1056` ceiling one day is 7.04M rows
and takes 8m 25s — a work unit long enough to leave a core busy while others idle at the tail
of a run, and an 85 MB gzip object no reader can split. `--split-hours 4` turns each of its
days into six ~2-minute units and ~14 MB objects.

Parallel efficiency is around 50% rather than linear: eight `vpc_flow_logs` partitions at
`--jobs 8` finished in 87s against 44s for one alone — 8× the work in 2× the time, with each
partition's own wall time doubling to ~86s. Each generator is internally multi-threaded (`-m`
sets the pool size) and the simulated clock serialises those threads through a shared lock, so
processes oversubscribe rather than each pinning one core cleanly.

That puts a full run at roughly 9 hours on a 12-core laptop, or under 3 hours on a 32-vCPU
instance. Sizing is guesswork until measured on the instance itself, so time one day first:

```bash
# One day of everything — extrapolate x90
time python tools/generate_lake.py --bucket my-lake --start 2026-05-27 --end 2026-05-27 --jobs 30
```

Set `--jobs` at or slightly above vCPU count; beyond that, per-partition latency grows without
raising throughput.

## Running on EC2

Nothing is staged locally, so instance disk only needs room for the repo — size the instance
for cores instead, since `--jobs` is what sets wall-clock time. Give the instance an IAM role
with `s3:PutObject` on the target prefix (plus `s3:ListBucket` if you use `--check-remote`);
boto3 picks the role up with no configuration. Run under `tmux` or `nohup` and keep the
manifest on the instance so an interrupted run can resume.

## Caveats

**`--seed` is not reliably reproducible for the ecommerce configs.** Two identical `-m 1` runs
diverge from line 8 onward, so a regenerated partition will not match the one it replaced.
`vpc_flow_logs` at `-m 66` was byte-identical across runs. Because of this the tool treats a
partition as write-once: a failed run uploads nothing and is retried whole, and `--overwrite`
replaces an object rather than reproducing it. `--seed-base` still gives each day a distinct
seed, which is useful for varying data day to day but not for exact reproduction.

**Each template is an independent generation pass.** The 11 ecommerce templates re-generate
their events from scratch, so the same day in `csv` and in `apache:access:json` holds different
events, and the ecommerce profiles account for roughly 90% of total compute. Rendering one pass
to several template sinks would cut that by ~10×, but it needs an engine change in
`ieg/core.py`.
