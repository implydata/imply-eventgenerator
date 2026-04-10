#!/usr/bin/env python3
"""Empirically measure how -m affects throughput, auto-detecting the Little's Law ceiling.

Two-phase approach:
  1. Discovery: geometrically doubles -m from --start-m until row count plateaus.
     This locates the Little's Law ceiling without requiring you to know L in advance.
  2. Sampling: selects up to --samples evenly log-spaced -m values across the discovered
     range [start_m, 2 × plateau_m] and re-runs those for the final table.

Within each run the simulated clock is tracked by reading the clock field from output
lines, giving a real progress bar (% of simulated window elapsed) rather than a spinner.

If the config has an ambiguous clock field, pass --clock-field explicitly.

Outputs CSV by default; use --markdown for a table suitable for preset docs.

Usage:
    python tools/bench_config.py -c presets/configs/vpc_flow_logs.json --clock-field start
    python tools/bench_config.py -c presets/configs/ecommerce.json --duration P1D
    python tools/bench_config.py -c presets/configs/ssh_auth.json --samples 6
"""

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone

import dateutil.parser
import isodate
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

err = Console(stderr=True)

DEFAULT_SEED = 42
DEFAULT_START = "2024-01-01T00:00:00"
DEFAULT_DURATION = "PT6H"
PLATEAU_THRESHOLD = 0.10
DEFAULT_PLATEAU_CONFIRM = 2
DEFAULT_MAX_M = 100_000
DEFAULT_SAMPLES = 10


# ---------------------------------------------------------------------------
# Clock field detection
# ---------------------------------------------------------------------------

def find_clock_field(config):
    """Locate the emitter output field that carries the simulated clock timestamp.

    Checks emitter dimensions for type='clock' first, then falls back to tracing
    state variables of type='clock' through to their emitter dimension references.

    Returns (field_name, candidates):
      - (name, [])           — unique match
      - (None, [c1, c2, …])  — ambiguous; caller should require --clock-field
      - (None, [])           — not found; caller should require --clock-field
    """
    # Method 1: direct clock dimension on emitter
    direct = []
    for emitter in config.get("emitters", []):
        for dim in emitter.get("dimensions", []):
            if dim.get("type") == "clock" and dim["name"] not in direct:
                direct.append(dim["name"])
    if direct:
        return (direct[0], []) if len(direct) == 1 else (None, direct)

    # Method 2: variable of type='clock' referenced by an emitter dimension
    clock_vars = {
        var["name"]
        for state in config.get("states", [])
        for var in state.get("variables", [])
        if var.get("type") == "clock"
    }
    if clock_vars:
        via_var = []
        for emitter in config.get("emitters", []):
            for dim in emitter.get("dimensions", []):
                if dim.get("type") == "variable" and dim.get("variable") in clock_vars:
                    if dim["name"] not in via_var:
                        via_var.append(dim["name"])
        if via_var:
            return (via_var[0], []) if len(via_var) == 1 else (None, via_var)

    return (None, [])


# ---------------------------------------------------------------------------
# Subprocess runner — streams stdout, updates Rich progress from sim timestamps
# ---------------------------------------------------------------------------

def run_one(config_path, m, duration_str, start_str, seed,
            clock_field, start_dt, end_dt,
            progress, run_task):
    """Run one generator invocation, streaming output for live progress."""
    cmd = [
        sys.executable, "generator.py",
        "-c", config_path,
        "-r", duration_str,
        "-s", start_str,
        f"--seed={seed}",
        f"-m={m}",
    ]
    t0 = time.perf_counter()
    row_count = 0
    duration_secs = (end_dt - start_dt).total_seconds()

    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, bufsize=1,
    ) as proc:
        assert proc.stdout is not None
        for raw in proc.stdout:
            raw = raw.rstrip("\n")
            if not raw:
                continue
            row_count += 1

            # Parse clock field → update per-run progress bar
            if clock_field and duration_secs > 0:
                try:
                    obj = json.loads(raw)
                    val = obj.get(clock_field)
                    if val is not None:
                        if isinstance(val, str):
                            sim_ts = dateutil.parser.isoparse(val)
                        elif isinstance(val, (int, float)):
                            sim_ts = datetime.fromtimestamp(val, tz=timezone.utc)
                        else:
                            sim_ts = None
                        if sim_ts is not None:
                            if sim_ts.tzinfo is None:
                                sim_ts = sim_ts.replace(tzinfo=timezone.utc)
                            elapsed_sim = (sim_ts - start_dt).total_seconds()
                            pct = max(0.0, min(100.0, elapsed_sim / duration_secs * 100))
                            progress.update(run_task, completed=pct)
                except Exception:
                    pass

        if proc.wait() != 0:
            raise RuntimeError(f"generator.py exited non-zero for -m {m}")

    elapsed_wall = time.perf_counter() - t0
    progress.update(run_task, completed=100.0)
    return row_count, elapsed_wall


# ---------------------------------------------------------------------------
# Plateau detection / sample-point generation
# ---------------------------------------------------------------------------

def is_plateau(prev_rows, curr_rows, threshold):
    if prev_rows is None or prev_rows == 0:
        return curr_rows == 0
    return (curr_rows - prev_rows) / prev_rows < threshold



def log_spaced_integers(lo, hi, n):
    """Up to n distinct integers, log-spaced from lo to hi inclusive."""
    if lo >= hi or n <= 1:
        return [lo] if lo <= hi else [hi]
    log_lo, log_hi = math.log(lo), math.log(hi)
    pts = set()
    for i in range(n):
        t = i / (n - 1)
        v = round(math.exp(log_lo + t * (log_hi - log_lo)))
        pts.add(max(lo, min(hi, v)))
    return sorted(pts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-c", "--config", required=True,
                        help="Path to generator config JSON")
    parser.add_argument("--duration", default=DEFAULT_DURATION,
                        help=f"Simulated window (ISO 8601 duration). Default: {DEFAULT_DURATION}")
    parser.add_argument("--start", default=DEFAULT_START,
                        help=f"Simulated start time (ISO 8601). Default: {DEFAULT_START}")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"Random seed. Default: {DEFAULT_SEED}")
    parser.add_argument("--start-m", type=int, default=1,
                        help="Smallest -m value to test. Default: 1")
    parser.add_argument("--max-m", type=int, default=DEFAULT_MAX_M,
                        help=f"Upper bound on -m during discovery. Default: {DEFAULT_MAX_M:,}")
    parser.add_argument("--plateau-threshold", type=float, default=PLATEAU_THRESHOLD,
                        help=f"Row-growth fraction below which a step is plateau. Default: {PLATEAU_THRESHOLD}")
    parser.add_argument("--plateau-confirm", type=int, default=DEFAULT_PLATEAU_CONFIRM,
                        help=f"Consecutive plateau readings before stopping. Default: {DEFAULT_PLATEAU_CONFIRM}")
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES,
                        help=f"Points in the final table. Default: {DEFAULT_SAMPLES}")
    parser.add_argument("--clock-field", default=None,
                        help="JSON field name carrying the simulated clock timestamp "
                             "(required if the config has multiple clock fields)")
    args = parser.parse_args()

    # --- Load config and resolve clock field ---
    with open(args.config) as f:
        config = json.load(f)

    if args.clock_field:
        clock_field = args.clock_field
    else:
        clock_field, candidates = find_clock_field(config)
        if clock_field is None:
            if candidates:
                parser.error(
                    f"Config has multiple clock fields: {candidates}. "
                    f"Specify one with --clock-field."
                )
            else:
                parser.error(
                    "Could not find a clock field in the config. "
                    "Specify one with --clock-field."
                )

    # --- Compute simulated time window ---
    start_dt = dateutil.parser.isoparse(args.start)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    end_dt = start_dt + isodate.parse_duration(args.duration)

    run_kwargs = dict(
        config_path=args.config,
        duration_str=args.duration,
        start_str=args.start,
        seed=args.seed,
        clock_field=clock_field,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=Console(stderr=True),
        transient=False,
    ) as progress:

        # ----------------------------------------------------------------
        # Phase 1: discovery (geometric doubling)
        # ----------------------------------------------------------------
        disc_task = progress.add_task("[cyan]Phase 1 — discovery", total=None)

        cache = {}  # m -> (rows, elapsed) — reused in sampling phase
        plateau_m = None
        plateau_run = 0
        prev_rows = None
        m = args.start_m

        while m <= args.max_m:
            progress.update(disc_task, description=f"[cyan]Phase 1 — discovery  -m {m:,}")
            run_task = progress.add_task(f"[dim]disc  -m {m:>8,}", total=100.0)

            rows, elapsed = run_one(m=m, **run_kwargs,
                                    progress=progress, run_task=run_task)
            cache[m] = (rows, elapsed)

            plat = is_plateau(prev_rows, rows, args.plateau_threshold)
            suffix = "  [yellow]← plateau[/yellow]" if plat else ""
            progress.update(
                run_task, completed=100.0,
                description=f"disc  -m {m:>8,}  {rows:>10,} rows  {elapsed:.1f}s{suffix}",
            )

            if plat:
                if plateau_m is None:
                    plateau_m = m
                plateau_run += 1
                if plateau_run >= args.plateau_confirm:
                    break
            else:
                plateau_run = 0

            prev_rows = rows
            next_m = m * 2
            if next_m > args.max_m:
                break
            m = next_m

        if plateau_m is None:
            plateau_m = m

        progress.update(disc_task, description="[cyan]Phase 1 — complete")

        # ----------------------------------------------------------------
        # Phase 2: sampling across discovered range
        # ----------------------------------------------------------------
        max_sample = min(plateau_m * 2, args.max_m)
        sample_points = log_spaced_integers(args.start_m, max_sample, args.samples)

        sample_task = progress.add_task(
            f"[green]Phase 2 — sampling  (plateau ~{plateau_m:,})",
            total=len(sample_points),
        )

        prev_rows = None
        for m in sample_points:
            if m in cache:
                rows, elapsed = cache[m]
                run_task = progress.add_task(f"[dim]sample-m {m:>8,}", total=100.0)
                progress.update(
                    run_task, completed=100.0,
                    description=f"sample -m {m:>8,}  {rows:>10,} rows  (cached)",
                )
            else:
                run_task = progress.add_task(f"[dim]sample -m {m:>8,}", total=100.0)
                rows, elapsed = run_one(m=m, **run_kwargs,
                                        progress=progress, run_task=run_task)
                progress.update(
                    run_task, completed=100.0,
                    description=f"sample -m {m:>8,}  {rows:>10,} rows  {elapsed:.1f}s",
                )

            results.append({"m": m, "rows": rows, "elapsed_s": elapsed})
            progress.advance(sample_task, 1)
            prev_rows = rows

        progress.update(sample_task, description="[green]Phase 2 — complete")

    # ----------------------------------------------------------------
    # Output
    # ----------------------------------------------------------------
    print()
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=["m", "rows", "elapsed_s"],
        lineterminator="\n",
    )
    writer.writeheader()
    for r in results:
        writer.writerow({
            "m": r["m"],
            "rows": r["rows"],
            "elapsed_s": f"{r['elapsed_s']:.1f}",
        })






if __name__ == "__main__":
    main()
