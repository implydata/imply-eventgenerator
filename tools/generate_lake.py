#!/usr/bin/env python3
"""Generate a date-partitioned datalake of synthetic events and upload it to S3.

One generator.py run per (profile, template, day), invoked as:

    generator.py -c <config> -t <template> -m <ceiling> -r P1D -s <day>T00:00:00

Because each run covers exactly one simulated day, the partition is decided by the
run's arguments — no timestamp parsing is needed, which matters because the presets
emit eleven different output shapes (NDJSON, CSV, NCSA combined, IIS, key-value).
Each run's stdout is gzipped in flight and uploaded as one object:

    s3://<bucket>/<prefix>/<profile>/<template>/<YYYY>/<MM>/<DD>/<profile>-<template>-<YYYYMMDD>.<ext>.gz

Runs are independent, so they parallelise across cores and resume cleanly: every
completed partition is appended to a JSONL manifest and skipped on re-run.

Usage:
    # Plan first — no generation, no uploads
    python tools/generate_lake.py --bucket my-lake --start 2026-05-27 --end 2026-08-24 --dry-run

    # Full run, 16 parallel generators
    python tools/generate_lake.py --bucket my-lake --start 2026-05-27 --end 2026-08-24 --jobs 16

    # One profile, to a local tree instead of S3 (smoke test)
    python tools/generate_lake.py --local-dir /tmp/lake --start 2026-05-27 --end 2026-05-28 \
        --profile ecommerce --template csv

Re-running the same command resumes: partitions already in the manifest are skipped.
"""

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "generator.py"
CONFIG_DIR = REPO_ROOT / "presets" / "configs"
SCHEDULE_DIR = REPO_ROOT / "presets" / "schedules"

# When stderr is piped, rich defaults to 80 columns and truncates the plan table.
err = Console(stderr=True, width=None if sys.stderr.isatty() else 140)

DEFAULT_JOBS = max(1, (os.cpu_count() or 2) - 2)
DEFAULT_COMPRESSLEVEL = 6
DEFAULT_MANIFEST = "lake_manifest.jsonl"
SPOOL_MAX = 64 * 1024 * 1024  # bytes held in memory before a partition spills to disk
READ_CHUNK = 1 << 20

# ---------------------------------------------------------------------------
# Per-profile generation settings
#
# 'm' is the concurrency ceiling — the point past which -m no longer raises
# throughput, so the interarrival mean becomes the binding constraint. Setting -m
# at (or above) the ceiling therefore yields the config's natural event volume.
# Ceilings come from docs/presets/<name>.md; measure with tools/bench_config.py.
#
# 'est_rows_per_hour' and 'est_bytes_per_row' drive --dry-run estimates only.
# ---------------------------------------------------------------------------
PROFILE_SETTINGS = {
    "ecommerce": {
        "m": 2112,
        "schedule": "ecommerce.json",
        "est_rows_per_hour": 22_200,
        "est_bytes_per_row": 275,
    },
    "ecommerce_lighting": {
        "m": 2112,
        "schedule": "ecommerce.json",
        "est_rows_per_hour": 29_100,
        "est_bytes_per_row": 275,
    },
    "ecommerce_furniture": {
        "m": 528,
        "schedule": "ecommerce.json",
        "est_rows_per_hour": 6_500,
        "est_bytes_per_row": 275,
    },
    "vpc_flow_logs": {
        "m": 66,
        "schedule": None,
        "est_rows_per_hour": 32_500,
        "est_bytes_per_row": 110,
    },
    # Ceiling probed at ~1056 (docs/presets doc still missing for this config).
    "vpc_flow_logs_derived": {
        "m": 1056,
        "schedule": None,
        "est_rows_per_hour": 288_000,
        "est_bytes_per_row": 110,
    },
    "endpoint_network": {
        "m": 1,
        "schedule": None,
        "est_rows_per_hour": 12_000,
        "est_bytes_per_row": 90,
    },
    "ssh_auth": {
        "m": 66,
        "schedule": None,
        "est_rows_per_hour": 850,
        "est_bytes_per_row": 94,
    },
    "pbx_calls": {
        "m": 9,
        "schedule": None,
        "est_rows_per_hour": 113,
        "est_bytes_per_row": 206,
    },
}

FALLBACK_SETTINGS = {
    "m": 100,
    "schedule": None,
    "est_rows_per_hour": 10_000,
    "est_bytes_per_row": 200,
}


@dataclass(frozen=True)
class Task:
    profile: str
    config: str
    template: str
    template_slug: str
    day: date
    hour: Optional[int]      # None when the partition covers the whole day
    runtime: str             # ISO 8601 duration passed to generator.py -r
    ext: str
    m: int
    schedule: Optional[str]
    seed: Optional[int]
    key: str


@dataclass
class Result:
    task: Task
    status: str
    rows: int = 0
    raw_bytes: int = 0
    gz_bytes: int = 0
    wall_s: float = 0.0
    detail: str = ""


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Make a template name safe for an object key ('ms:iis:default:85' -> 'ms_iis_default_85')."""
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()


def infer_extension(template_name: str, template_def: dict) -> str:
    """Guess the file extension for a template's output.

    Configs carry no format metadata — only an optional 'header' — so this keys off
    the template name and the shape of the header line.
    """
    name = template_name.lower()
    header = (template_def or {}).get("header", "")
    if "json" in name:
        return "json"
    if name == "csv" or (header and "," in header and not header.lstrip().startswith("#")):
        return "csv"
    return "log"


def build_key(prefix: str, task_profile: str, template_slug: str, day: date,
              hour: Optional[int], ext: str) -> str:
    stamp = day.strftime("%Y%m%d") + ("" if hour is None else f"T{hour:02d}")
    parts = [
        task_profile,
        template_slug,
        f"{day.year:04d}",
        f"{day.month:02d}",
        f"{day.day:02d}",
        f"{task_profile}-{template_slug}-{stamp}.{ext}.gz",
    ]
    if prefix:
        parts.insert(0, prefix.strip("/"))
    return "/".join(parts)


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------

class S3Sink:
    """Uploads each partition as a single S3 object."""

    def __init__(self, bucket, storage_class=None, sse=None, kms_key=None, acl=None):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:  # pragma: no cover - dependency guard
            raise SystemExit(
                "boto3 is required for S3 output. Install it with:\n"
                "    pip install -r requirements.txt\n"
                "Or write locally instead with --local-dir."
            ) from e
        self.bucket = bucket
        # max_pool_connections must cover --jobs so parallel uploads don't queue.
        self._client = boto3.client(
            "s3",
            config=Config(retries={"max_attempts": 10, "mode": "adaptive"}, max_pool_connections=64),
        )
        self.extra_args = {}
        if storage_class:
            self.extra_args["StorageClass"] = storage_class
        if sse:
            self.extra_args["ServerSideEncryption"] = sse
        if kms_key:
            self.extra_args["SSEKMSKeyId"] = kms_key
        if acl:
            self.extra_args["ACL"] = acl

    def describe(self):
        return f"s3://{self.bucket}"

    def preflight(self):
        # A write-only role can't HeadBucket (it maps to s3:ListBucket), so a failure
        # here is a warning, not a hard stop — the first upload is the real test.
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception as e:
            err.print(f"[yellow]could not verify bucket '{self.bucket}' ({type(e).__name__}) — "
                      f"continuing; uploads will fail fast if it is wrong[/yellow]")

    def exists(self, key):
        from botocore.exceptions import ClientError
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put(self, key, fileobj, content_type):
        # Deliberately no ContentEncoding: readers should treat these as opaque .gz
        # objects, not transparently-decompressed bodies.
        extra = dict(self.extra_args, ContentType=content_type)
        self._client.upload_fileobj(fileobj, self.bucket, key, ExtraArgs=extra)


class LocalSink:
    """Writes the same partition tree to a local directory — for smoke tests."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def describe(self):
        return str(self.root)

    def preflight(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def exists(self, key):
        return (self.root / key).exists()

    def put(self, key, fileobj, content_type):
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".partial")
        with open(tmp, "wb") as out:
            while True:
                chunk = fileobj.read(READ_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
        os.replace(tmp, dest)  # only a complete partition becomes visible


CONTENT_TYPES = {"json": "application/x-ndjson", "csv": "text/csv", "log": "text/plain"}


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def iter_days(start: date, end: date):
    """Yield every day from start to end, inclusive."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def load_profiles(only, exclude):
    """Return {profile: (config_path, {template_name: template_def})} for selected configs."""
    profiles = {}
    for path in sorted(CONFIG_DIR.glob("*.json")):
        name = path.stem
        if only and name not in only:
            continue
        if name in exclude:
            continue
        with open(path) as f:
            config = json.load(f)
        templates = config.get("templates") or {}
        if not templates:
            err.print(f"[yellow]skipping {name}: config has no templates block[/yellow]")
            continue
        profiles[name] = (path, templates)
    return profiles


def build_tasks(profiles, days, template_filter, prefix, seed_base, m_override,
                no_schedule, split_hours):
    tasks = []
    unknown = []
    for profile, (config_path, templates) in sorted(profiles.items()):
        settings = PROFILE_SETTINGS.get(profile)
        if settings is None:
            unknown.append(profile)
            settings = FALLBACK_SETTINGS
        m = m_override or settings["m"]
        schedule = None
        if settings["schedule"] and not no_schedule:
            schedule = str(SCHEDULE_DIR / settings["schedule"])
        for template_name, template_def in templates.items():
            if template_filter and template_name not in template_filter:
                continue
            slug = slugify(template_name)
            ext = infer_extension(template_name, template_def)
            for day in days:
                for hour in range(0, 24, split_hours):
                    marker = None if split_hours == 24 else hour
                    seed = None if seed_base is None else seed_base + day.toordinal() * 24 + hour
                    tasks.append(
                        Task(
                            profile=profile,
                            config=str(config_path),
                            template=template_name,
                            template_slug=slug,
                            day=day,
                            hour=marker,
                            runtime=f"PT{split_hours}H",
                            ext=ext,
                            m=m,
                            schedule=schedule,
                            seed=seed,
                            key=build_key(prefix, profile, slug, day, marker, ext),
                        )
                    )
    if unknown:
        err.print(
            f"[yellow]no PROFILE_SETTINGS entry for: {', '.join(unknown)} — "
            f"using -m {FALLBACK_SETTINGS['m']}. Run tools/bench_config.py to find the "
            f"real ceiling, then add it to PROFILE_SETTINGS.[/yellow]"
        )
    return tasks


def summarise_plan(tasks, sink, n_days, split_hours):
    """Print the plan: partitions and estimated volume per profile."""
    window = "1 object/day" if split_hours == 24 else f"{24 // split_hours} objects/day"
    table = Table(title=f"Plan — {len(tasks)} partitions over {n_days} days "
                        f"({window}) -> {sink.describe()}")
    table.add_column("profile")
    table.add_column("tmpl", justify="right")
    table.add_column("parts", justify="right")
    table.add_column("rows", justify="right")
    table.add_column("raw", justify="right")
    table.add_column("gzip", justify="right")
    table.add_column("-m", justify="right")
    table.add_column("schedule")

    total_rows = total_raw = 0
    by_profile = {}
    for t in tasks:
        by_profile.setdefault(t.profile, []).append(t)

    for profile, group in sorted(by_profile.items()):
        settings = PROFILE_SETTINGS.get(profile, FALLBACK_SETTINGS)
        n_templates = len({t.template for t in group})
        rows = settings["est_rows_per_hour"] * split_hours * len(group)
        raw = rows * settings["est_bytes_per_row"]
        total_rows += rows
        total_raw += raw
        table.add_row(
            profile,
            str(n_templates),
            str(len(group)),
            f"{rows:,}",
            human_bytes(raw),
            human_bytes(raw / 10),
            str(group[0].m),
            Path(group[0].schedule).name if group[0].schedule else "-",
        )
    table.add_section()
    table.add_row(
        "TOTAL", "", str(len(tasks)), f"{total_rows:,}", human_bytes(total_raw),
        human_bytes(total_raw / 10), "", "",
    )
    err.print(table)
    err.print(
        "[dim]Estimates use measured rates for the ecommerce schedule and assume a 10:1 "
        "gzip ratio (measured 10-13:1). Actual volume varies with -m and schedule.[/dim]"
    )


def human_bytes(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:,.1f} {unit}" if unit != "B" else f"{n:,.0f} B"
        n /= 1024


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def run_task(task: Task, sink, compresslevel, timeout, stop: threading.Event) -> Result:
    """Generate one day of one template and upload it as a single gzipped object."""
    if stop.is_set():
        return Result(task, "cancelled")

    cmd = [
        sys.executable, str(GENERATOR),
        "-c", task.config,
        "-t", task.template,
        "-m", str(task.m),
        "-r", task.runtime,
        "-s", f"{task.day.isoformat()}T{(task.hour or 0):02d}:00:00",
    ]
    if task.schedule:
        cmd += ["--schedule", task.schedule]
    if task.seed is not None:
        cmd += ["--seed", str(task.seed)]

    started = time.time()
    rows = raw_bytes = 0
    killed = False

    with tempfile.TemporaryFile() as errfile, \
            tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX, mode="w+b") as spool:
        # mtime=0 keeps the gzip header byte-stable for identical input.
        gz = gzip.GzipFile(filename="", mode="wb", fileobj=spool, compresslevel=compresslevel, mtime=0)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errfile, cwd=str(REPO_ROOT))
        try:
            while True:
                chunk = proc.stdout.read(READ_CHUNK)
                if not chunk:
                    break
                rows += chunk.count(b"\n")
                raw_bytes += len(chunk)
                gz.write(chunk)
                if stop.is_set() or (timeout and time.time() - started > timeout):
                    killed = True
                    proc.kill()
                    break
        finally:
            proc.stdout.close()
        rc = proc.wait()
        gz.close()

        if killed:
            return Result(task, "cancelled" if stop.is_set() else "timeout", rows, raw_bytes,
                          wall_s=time.time() - started,
                          detail=f"killed after {time.time() - started:.0f}s")
        if rc != 0:
            errfile.seek(0)
            tail = errfile.read()[-2000:].decode("utf-8", "replace").strip()
            return Result(task, "failed", rows, raw_bytes, wall_s=time.time() - started,
                          detail=f"generator exit {rc}: {tail}")
        if rows == 0:
            errfile.seek(0)
            tail = errfile.read()[-2000:].decode("utf-8", "replace").strip()
            return Result(task, "empty", 0, 0, wall_s=time.time() - started,
                          detail=f"generator produced no records: {tail}")

        gz_bytes = spool.tell()
        spool.seek(0)
        try:
            sink.put(task.key, spool, CONTENT_TYPES.get(task.ext, "text/plain"))
        except Exception as e:
            return Result(task, "upload_failed", rows, raw_bytes, gz_bytes,
                          time.time() - started, f"{type(e).__name__}: {e}")

    return Result(task, "ok", rows, raw_bytes, gz_bytes, time.time() - started)


def load_manifest(path):
    """Return the set of keys already written successfully."""
    done = set()
    if not path or not os.path.exists(path):
        return done
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("status") == "ok" and rec.get("key"):
                done.add(rec["key"])
    return done


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_day(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got '{value}'")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Generate a date-partitioned datalake of synthetic events into S3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[-1],
    )
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--bucket", help="Destination S3 bucket")
    dest.add_argument("--local-dir", help="Write the partition tree to a local directory instead of S3")

    p.add_argument("--prefix", default="", help="Key prefix within the bucket (default: bucket root)")
    p.add_argument("--start", type=parse_day, required=True, help="First day to generate (YYYY-MM-DD)")
    p.add_argument("--end", type=parse_day, required=True, help="Last day to generate, inclusive (YYYY-MM-DD)")

    p.add_argument("--profile", action="append", default=[],
                   help="Only this profile (config basename); repeatable. Default: all configs.")
    p.add_argument("--exclude-profile", action="append", default=[], help="Skip this profile; repeatable")
    p.add_argument("--template", action="append", default=[],
                   help="Only this template name; repeatable. Default: every template in each config.")

    p.add_argument("--jobs", type=int, default=DEFAULT_JOBS,
                   help=f"Parallel generator processes (default: {DEFAULT_JOBS} — cores minus 2)")
    p.add_argument("-m", "--concurrency", type=int, default=None,
                   help="Override -m for every profile. Default: each profile's measured ceiling.")
    p.add_argument("--split-hours", type=int, default=24, choices=[1, 2, 3, 4, 6, 8, 12, 24],
                   help="Split each day into objects of this many hours (default: 24, one object "
                        "per day). Smaller values give finer parallelism and smaller objects, at "
                        "the cost of a worker ramp-up and truncated sessions at every boundary.")
    p.add_argument("--no-schedule", action="store_true",
                   help="Ignore per-profile schedules (raises ecommerce volume by ~1.5x)")
    p.add_argument("--seed-base", type=int, default=None,
                   help="Derive each day's --seed as seed-base + day ordinal. Note: --seed is not "
                        "reliably reproducible for the ecommerce configs.")

    p.add_argument("--compresslevel", type=int, default=DEFAULT_COMPRESSLEVEL,
                   help=f"gzip level 1-9 (default: {DEFAULT_COMPRESSLEVEL})")
    p.add_argument("--storage-class", default=None, help="S3 storage class (e.g. STANDARD_IA)")
    p.add_argument("--sse", default=None, help="Server-side encryption (e.g. AES256, aws:kms)")
    p.add_argument("--kms-key-id", default=None, help="KMS key id when --sse aws:kms")
    p.add_argument("--acl", default=None, help="Object ACL (e.g. bucket-owner-full-control)")

    p.add_argument("--manifest", default=DEFAULT_MANIFEST,
                   help=f"JSONL run log, also used for resume (default: {DEFAULT_MANIFEST})")
    p.add_argument("--overwrite", action="store_true", help="Regenerate partitions already in the manifest")
    p.add_argument("--check-remote", action="store_true",
                   help="Also skip partitions that already exist at the destination (one HEAD per partition)")
    p.add_argument("--task-timeout", type=int, default=0,
                   help="Kill a single partition after N seconds (default: 0, no limit)")
    p.add_argument("--dry-run", action="store_true", help="Print the plan and exit without generating")

    args = p.parse_args(argv)

    if args.end < args.start:
        p.error(f"--end ({args.end}) is before --start ({args.start})")
    if not 1 <= args.compresslevel <= 9:
        p.error("--compresslevel must be 1-9")
    if args.jobs < 1:
        p.error("--jobs must be >= 1")

    days = list(iter_days(args.start, args.end))
    profiles = load_profiles(set(args.profile), set(args.exclude_profile))
    if not profiles:
        err.print("[red]no matching profiles in presets/configs[/red]")
        return 1

    tasks = build_tasks(
        profiles, days, set(args.template), args.prefix,
        args.seed_base, args.concurrency, args.no_schedule, args.split_hours,
    )
    if not tasks:
        err.print("[red]no partitions to generate — check --profile / --template[/red]")
        return 1

    sink = LocalSink(args.local_dir) if args.local_dir else S3Sink(
        args.bucket, args.storage_class, args.sse, args.kms_key_id, args.acl)

    summarise_plan(tasks, sink, len(days), args.split_hours)
    err.print(f"[dim]example key: {tasks[0].key}[/dim]")

    if args.dry_run:
        err.print("[cyan]--dry-run: nothing generated[/cyan]")
        return 0

    sink.preflight()

    skipped = 0
    if not args.overwrite:
        done = load_manifest(args.manifest)
        if done:
            before = len(tasks)
            tasks = [t for t in tasks if t.key not in done]
            skipped += before - len(tasks)
        if args.check_remote:
            remaining = []
            for t in tasks:
                if sink.exists(t.key):
                    skipped += 1
                else:
                    remaining.append(t)
            tasks = remaining
        if skipped:
            err.print(f"[cyan]resuming: {skipped} partitions already complete, {len(tasks)} to go[/cyan]")
    if not tasks:
        err.print("[green]nothing to do — every partition is already complete[/green]")
        return 0

    stop = threading.Event()
    manifest_lock = threading.Lock()
    totals = {"ok": 0, "rows": 0, "raw": 0, "gz": 0}
    failures = []
    run_started = time.time()

    manifest_file = open(args.manifest, "a", buffering=1) if args.manifest else None

    def record(result: Result):
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "status": result.status,
            "key": result.task.key,
            "profile": result.task.profile,
            "template": result.task.template,
            "day": result.task.day.isoformat(),
            "hour": result.task.hour,
            "rows": result.rows,
            "raw_bytes": result.raw_bytes,
            "gz_bytes": result.gz_bytes,
            "wall_s": round(result.wall_s, 1),
            "m": result.task.m,
            "schedule": Path(result.task.schedule).name if result.task.schedule else None,
            "seed": result.task.seed,
        }
        if result.detail:
            rec["detail"] = result.detail
        if manifest_file:
            with manifest_lock:
                manifest_file.write(json.dumps(rec) + "\n")

    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        TextColumn("{task.fields[status]}"),
        console=err,
    )

    try:
        with progress:
            bar = progress.add_task("partitions", total=len(tasks), status="")
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                futures = {pool.submit(run_task, t, sink, args.compresslevel,
                                       args.task_timeout, stop): t for t in tasks}
                try:
                    for fut in as_completed(futures):
                        result = fut.result()
                        record(result)
                        if result.status == "ok":
                            totals["ok"] += 1
                            totals["rows"] += result.rows
                            totals["raw"] += result.raw_bytes
                            totals["gz"] += result.gz_bytes
                        elif result.status != "cancelled":
                            failures.append(result)
                            err.print(f"[red]{result.status}[/red] {result.task.key}: {result.detail}")
                        progress.update(
                            bar, advance=1,
                            status=f"{human_bytes(totals['gz'])} gz | {totals['rows']:,} rows"
                                   + (f" | [red]{len(failures)} failed[/red]" if failures else ""),
                        )
                except KeyboardInterrupt:
                    stop.set()
                    err.print("[yellow]interrupted — finishing in-flight partitions, "
                              "re-run the same command to resume[/yellow]")
                    for fut in futures:
                        fut.cancel()
                    raise
    except KeyboardInterrupt:
        pass
    finally:
        if manifest_file:
            manifest_file.close()

    elapsed = time.time() - run_started
    err.print()
    err.print(f"[green]uploaded[/green] {totals['ok']:,}/{len(tasks):,} partitions to {sink.describe()}")
    err.print(f"  rows      {totals['rows']:,}")
    err.print(f"  raw       {human_bytes(totals['raw'])}")
    err.print(f"  gzipped   {human_bytes(totals['gz'])}"
              + (f" ({totals['raw'] / totals['gz']:.1f}:1)" if totals["gz"] else ""))
    err.print(f"  wall      {timedelta(seconds=int(elapsed))} at {args.jobs} jobs")
    err.print(f"  manifest  {args.manifest}")
    if failures:
        err.print(f"[red]{len(failures)} partitions failed[/red] — re-run the same command to retry them")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
