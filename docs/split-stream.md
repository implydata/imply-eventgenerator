# Splitting a run into partitions

`tools/split_stream.sh` runs a `generator.py` command and splits its stdout into calendar-partitioned, gzipped files — one continuous run in, a directory tree of per-day (or per-hour) files out.

## Why

Bulk-exporting historical data means covering a wide date range, but a single `generator.py` process can only run for as long as its `-r` duration allows before it has to stop. The obvious fix — one process per day — works, but each process starts with an empty worker pool that has to ramp up, and cuts off any session in flight at the boundary, every single day.

Running one continuous process for the whole range avoids both problems, but then something has to split the output into per-day files afterwards. The presets in this repo render 11 different output shapes (NDJSON, CSV, NCSA combined log, IIS, key-value, syslog-style positional text), several with no discrete timestamp field at all — so a splitter that parses timestamps out of the rendered records isn't generically possible.

`-p`/`--partition` (see [generator-config.md](./generator-config.md)) sidesteps this: `generator.py` itself emits a marker line into its own output stream whenever simulated time crosses a partition boundary, since it's the one thing that already knows true simulated time. `split_stream.sh` never looks at record content — it splits purely on that marker, using GNU `csplit`.

## Requirements

GNU `csplit`. The BSD `csplit` that ships by default on macOS lacks features this script needs. If you're on macOS:

```bash
brew install coreutils
```

This installs GNU `csplit` as `gcsplit`, picked up automatically alongside the system `csplit` — no `$PATH` changes needed. On Linux, GNU coreutils is normally already the system default.

## Usage

```text
tools/split_stream.sh --out <dir> [--prefix <name>] [--ext <ext>] -- <generator.py command...>
```

| Option | Description |
| --- | --- |
| `--out <dir>` | Output root. Files are written to `<dir>/YYYY/MM/DD/<prefix->stamp.ext.gz`. Required. |
| `--prefix <name>` | Prefix for each output filename, e.g. `profile-template`. Optional; omit for just `<stamp>.ext.gz`. |
| `--ext <ext>` | File extension before `.gz`, e.g. `json`, `csv`, `log`. Default: `log`. |

Everything after `--` is the `generator.py` command to run. It must itself include `-p`/`--partition` — without it, stdout has no marker to split on, and the script fails with a clear error rather than silently writing the whole run as one file.

```bash
tools/split_stream.sh --out out/vpc_flow_logs --prefix vpc_flow_logs-aws_cloudwatchlogs_vpcflow --ext log -- \
  python generator.py -c presets/configs/vpc_flow_logs.json -t aws:cloudwatchlogs:vpcflow \
    -w 66 -r P7D -s 2026-05-27T00:00:00 -p P1D
```

produces:

```text
out/vpc_flow_logs/2026/05/27/vpc_flow_logs-aws_cloudwatchlogs_vpcflow-20260527T000000.log.gz
out/vpc_flow_logs/2026/05/28/vpc_flow_logs-aws_cloudwatchlogs_vpcflow-20260528T000000.log.gz
...
```

## How it works

The marker line is kept in `csplit`'s output, not discarded — it's the first line of each split segment, so that segment's own boundary timestamp names the file with no reformatting needed. For each segment: read the first line, extract the timestamp, strip that line from the body, gzip what's left, and write it to `<out>/YYYY/MM/DD/`.

Each marker is followed immediately by the active template's header (if it has one), emitted by `generator.py` itself at that same boundary — so every split file is complete and valid on its own, without `split_stream.sh` needing any per-template knowledge of what a header looks like.

Because a partition marker is only ever emitted right before the record that triggers it (see [generator-config.md](./generator-config.md)), a segment is never empty — there's no equivalent of an empty trailing file to filter out.

## Copying to S3

`split_stream.sh` only writes to a local directory. Getting that directory into S3 is a separate step, and `aws s3 sync` handles it well:

```bash
aws s3 sync out/vpc_flow_logs s3://my-lake/eventgen/vpc_flow_logs --exclude "*" --include "*.gz"
```

A few things worth knowing before relying on it:

- **It's resumable.** `sync` compares local files against the destination (by size and modification time) and only transfers what's missing or changed — re-running the same command after an interruption picks up where it left off, with nothing extra to track.
- **It's additive by default, not a mirror.** Objects that exist at the destination but not in the local source are left alone; `sync` never deletes anything unless you pass `--delete`. If you do need mirror behavior, run with `--dryrun` first to see exactly what would be deleted before it happens.
- **It's direction-agnostic.** The same command works local-to-S3, S3-to-local (`aws s3 sync s3://my-lake/eventgen/vpc_flow_logs out/vpc_flow_logs`), or bucket-to-bucket — source and destination are just positional arguments, either can be local or `s3://`.
- **It matches by exact key, not by day.** If you're adding to a bucket that already has data for the same date range from a different tool or an older filename convention, check the key format matches before assuming a re-run will replace what's there — `sync` treats a differently-named file as a new object to add alongside the old one, not a replacement for it, even if both cover the same day.
- **`--exclude "*" --include "*.gz"` keeps out anything that isn't real output** — a `.DS_Store` from Finder browsing the local directory, a leftover `.partial` from an interrupted write, an editor swap file. Order matters: later filters override earlier ones for files they both match, so `--exclude "*"` has to come *before* `--include "*.gz"` — reversed, the trailing `--exclude "*"` would win and nothing would upload. `--include` alone does nothing, since every file is included by default until something excludes it first.

## See also

- [generator-config.md](./generator-config.md) — `-p`/`--partition`
- [generate-all.md](./generate-all.md) — running this across every preset and template in one pass
