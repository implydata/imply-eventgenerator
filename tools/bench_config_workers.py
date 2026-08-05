#!/usr/bin/env python3
"""Empirically measure how -w (workers, alias -m) affects throughput, finding the
concurrency ceiling at a given -i.

Three-phase approach:
  1. Discovery: geometrically doubles -w from --start-m until row count plateaus.
  2. Refinement: binary-searches between the last non-plateau and first plateau value
     to pinpoint the ceiling precisely (within ~5%).
  3. Sampling: selects up to --samples evenly log-spaced -w values across
     [start_m, 2 × ceiling] and runs those for the final table.

Within each run the simulated clock is tracked by reading the clock field from output
lines, giving a real progress bar (% of simulated window elapsed) rather than a spinner.

If the config has an ambiguous clock field, pass --clock-field explicitly.

By default, -w is measured at the preset's own event:start:timer interval. Pass -i to
override it (same flag, same meaning, as generator.py's own -i) -- e.g. to find the
ceiling at a hypothetically faster or slower arrival rate. This is the -w counterpart
of bench_config_interval.py, which finds the -i floor at a given -w.

Outputs CSV to stdout and an empirical summary (ceiling, regenerate command) to stderr.

Usage:
    python tools/bench_config_workers.py -c presets/configs/vpc_flow_logs.json --clock-field start
    python tools/bench_config_workers.py -c presets/configs/ecommerce.json --duration P1D
    python tools/bench_config_workers.py -c presets/configs/ssh_auth.json --samples 6
    python tools/bench_config_workers.py -c presets/configs/ecommerce.json -i 5
"""

import argparse
import csv
import json
import logging
import math
import os
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
logger = logging.getLogger(__name__)

DEFAULT_SEED = 42
DEFAULT_START = "2024-01-01T00:00:00"
DEFAULT_DURATION = "PT6H"
PLATEAU_THRESHOLD = 0.10
DEFAULT_MAX_M = 10_000  # matches generator.py's own -w hard cap (MAX_WORKERS) — kept as an
# independent constant rather than imported, same as MEAN_FIELD_BY_TYPE below: this file
# treats generator.py as an opaque subprocess, not a library. A discovery value beyond
# this would just get rejected by generator.py's own CLI validation.
DEFAULT_SAMPLES = 10
PLOT_COLOR = "#2563eb"  # xychart-beta's default single-series line color is a pale
# theme-dependent blue/grey that's low-contrast in most renderers (VS Code's preview
# included) -- overridden via plotColorPalette rather than relying on the theme.

# Mirrors generator.py's apply_start_interval_override dispatch — kept independent
# since bench_config_workers.py treats generator.py as an opaque subprocess, not a library.
MEAN_FIELD_BY_TYPE = {
    "constant": "value",
    "exponential": "mean",
    "normal": "mean",
    "gmm_temporal": "mean",
}


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


def validate_start_interval(value):
    try:
        fvalue = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Start interval must be a number.")
    if fvalue <= 0:
        raise argparse.ArgumentTypeError("Start interval must be greater than 0.")
    return fvalue


def get_start_interval_value(config):
    """Return the event:start:timer state's current interval value.

    Mirrors generator.py's apply_start_interval_override dispatch: 'constant' reads
    'value', 'exponential'/'normal'/'gmm_temporal' read 'mean'. Raises ValueError for
    an unsupported distribution (e.g. 'uniform') or a missing start-timer state.
    """
    timer_state = next(
        (s for s in config.get("states", []) if s.get("type") == "event:start:timer"), None
    )
    if timer_state is None:
        raise ValueError("Config has no event:start:timer state.")

    dist = timer_state.get("cardinality_distribution", {})
    dist_type = dist.get("type")
    field = MEAN_FIELD_BY_TYPE.get(dist_type)
    if field is None:
        raise ValueError(
            f"Reading (or overriding, with -i) the event:start:timer state's start "
            f"interval requires cardinality_distribution type '{dist_type}' to be "
            f"one of the supported types: {sorted(MEAN_FIELD_BY_TYPE)}."
        )
    return dist[field]


# ---------------------------------------------------------------------------
# Subprocess runner — streams stdout, updates Rich progress from sim timestamps
# ---------------------------------------------------------------------------

def run_one(config_path, m, duration_str, start_str, seed,
            clock_field, start_dt, end_dt,
            progress, run_task, start_interval=None):
    """Run one generator invocation, streaming output for live progress."""
    cmd = [
        sys.executable, "generator.py",
        "-c", config_path,
        "-r", duration_str,
        "-s", start_str,
        f"--seed={seed}",
        f"-w={m}",
    ]
    if start_interval is not None:
        cmd.append(f"-i={start_interval}")
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
            raise RuntimeError(f"generator.py exited non-zero for -w {m}")

    elapsed_wall = time.perf_counter() - t0
    progress.update(run_task, completed=100.0)
    return row_count, elapsed_wall


# ---------------------------------------------------------------------------
# Plateau detection / sample-point generation
# ---------------------------------------------------------------------------

def is_plateau(prev_rows, curr_rows, threshold):
    """True if curr_rows is within `threshold` of prev_rows, in EITHER direction.

    Must use abs() here: with a fixed seed but multiple worker threads sharing one
    RNG stream, changing -w changes thread-dispatch interleaving, which changes which
    random draws land on which session — so row counts aren't perfectly monotonic in
    -w. A plain (curr - prev) / prev < threshold treats any decrease as "plateaued"
    (a negative number is always < a positive threshold), which can lock the
    binary-search refinement onto a noise dip well before the real plateau.
    """
    if prev_rows is None or prev_rows == 0:
        return curr_rows == 0
    return abs(curr_rows - prev_rows) / prev_rows < threshold


def nice_ceil(value, headroom=0.15):
    """Round value × (1 + headroom) up to 2 significant figures."""
    raw = value * (1 + headroom)
    if raw <= 0:
        return 1
    magnitude = 10 ** (math.floor(math.log10(raw)) - 1)
    return math.ceil(raw / magnitude) * magnitude


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
# Phase 1 + 1b: discovery + binary-search refinement → the -w ceiling
# ---------------------------------------------------------------------------

def find_ceiling(run_kwargs, args, progress, start_interval=None):
    """Discover and refine the -w ceiling at the given -i.

    Returns (plateau_m, cache) where cache maps m -> (rows, elapsed_s), reusable
    by the sampling phase.
    """
    disc_task = progress.add_task("[cyan]Phase 1 — discovery", total=None)

    cache = {}
    plateau_m = None
    prev_rows = None
    last_non_plateau_m = args.start_m
    m = args.start_m

    while m <= args.max_m:
        progress.update(disc_task, description=f"[cyan]Phase 1 — discovery  -w {m:,}")
        run_task = progress.add_task(f"[dim]disc  -w {m:>8,}", total=100.0)

        rows, elapsed = run_one(m=m, **run_kwargs, start_interval=start_interval,
                                progress=progress, run_task=run_task)
        cache[m] = (rows, elapsed)

        plat = is_plateau(prev_rows, rows, args.plateau_threshold)
        suffix = "  [yellow]← plateau[/yellow]" if plat else ""
        progress.update(
            run_task, completed=100.0,
            description=f"disc  -w {m:>8,}  {rows:>10,} rows  {elapsed:.1f}s{suffix}",
        )

        if plat:
            plateau_m = m
            break
        else:
            last_non_plateau_m = m

        prev_rows = rows
        next_m = m * 2
        if next_m > args.max_m:
            break
        m = next_m

    if plateau_m is None:
        plateau_m = m

    progress.update(disc_task, description="[cyan]Phase 1 — complete")

    # Phase 1b: binary-search refinement — narrows the plateau boundary.
    # Doubling leaves up to a 2× gap. We bisect [last_non_plateau_m, plateau_m]
    # anchoring each comparison to the known-non-plateau rows so the
    # is_plateau check stays consistent.
    lo, hi = last_non_plateau_m, plateau_m
    lo_rows = cache[lo][0]

    if hi > lo + 1:
        refine_task = progress.add_task(
            f"[cyan]Phase 1b — refining  [{lo:,} … {hi:,}]", total=None
        )
        while hi > lo + 1 and hi / lo > 1.05:
            mid = (lo + hi) // 2
            if mid == lo or mid == hi:
                break
            progress.update(
                refine_task,
                description=f"[cyan]Phase 1b — refining  [{lo:,} … {hi:,}]  trying {mid:,}",
            )
            run_task = progress.add_task(f"[dim]refine -w {mid:>8,}", total=100.0)
            mid_rows, mid_elapsed = run_one(m=mid, **run_kwargs, start_interval=start_interval,
                                            progress=progress, run_task=run_task)
            cache[mid] = (mid_rows, mid_elapsed)

            if is_plateau(lo_rows, mid_rows, args.plateau_threshold):
                hi = mid
                plateau_m = mid
                suffix = "  [yellow]← plateau[/yellow]"
            else:
                lo = mid
                lo_rows = mid_rows
                suffix = ""
            progress.update(
                run_task, completed=100.0,
                description=f"refine -w {mid:>8,}  {mid_rows:>10,} rows  {mid_elapsed:.1f}s{suffix}",
            )

        progress.update(
            refine_task,
            description=f"[cyan]Phase 1b — complete  (ceiling ~{plateau_m:,})",
        )

    return plateau_m, cache


# ---------------------------------------------------------------------------
# Phase 2: sampling at a given set of -w points (reusing any cached runs)
# ---------------------------------------------------------------------------

def sample_at_points(run_kwargs, sample_points, cache, progress, plateau_m, start_interval=None):
    results = []

    sample_task = progress.add_task(
        f"[green]Phase 2 — sampling  (plateau ~{plateau_m:,})",
        total=len(sample_points),
    )

    for m in sample_points:
        if m in cache:
            rows, elapsed = cache[m]
            run_task = progress.add_task(f"[dim]sample-w {m:>8,}", total=100.0)
            progress.update(
                run_task, completed=100.0,
                description=f"sample -w {m:>8,}  {rows:>10,} rows  (cached)",
            )
        else:
            run_task = progress.add_task(f"[dim]sample -w {m:>8,}", total=100.0)
            rows, elapsed = run_one(m=m, **run_kwargs, start_interval=start_interval,
                                    progress=progress, run_task=run_task)
            progress.update(
                run_task, completed=100.0,
                description=f"sample -w {m:>8,}  {rows:>10,} rows  {elapsed:.1f}s",
            )

        results.append({"m": m, "rows": rows, "elapsed_s": elapsed})
        progress.advance(sample_task, 1)

    progress.update(sample_task, description="[green]Phase 2 — complete")
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stderr)

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-c", "--config", required=True,
                        help="Path to generator config JSON")
    parser.add_argument("-i", dest="start_interval", type=validate_start_interval, default=None,
                        help="Override the event:start:timer state's interarrival period "
                             "(seconds). Default: the config's own value.")
    parser.add_argument("--duration", default=DEFAULT_DURATION,
                        help=f"Simulated window (ISO 8601 duration). Default: {DEFAULT_DURATION}")
    parser.add_argument("--start", default=DEFAULT_START,
                        help=f"Simulated start time (ISO 8601). Default: {DEFAULT_START}")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"Random seed. Default: {DEFAULT_SEED}")
    parser.add_argument("--start-m", type=int, default=1,
                        help="Smallest -w value to test. Default: 1")
    parser.add_argument("--max-m", type=int, default=DEFAULT_MAX_M,
                        help=f"Upper bound on -w during discovery. Default: {DEFAULT_MAX_M:,}")
    parser.add_argument("--plateau-threshold", type=float, default=PLATEAU_THRESHOLD,
                        help=f"Row-growth fraction below which a step is plateau. Default: {PLATEAU_THRESHOLD}")

    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES,
                        help=f"Points in the final table. Default: {DEFAULT_SAMPLES}")
    parser.add_argument("--clock-field", default=None,
                        help="JSON field name carrying the simulated clock timestamp "
                             "(required if the config has multiple clock fields)")
    parser.add_argument("--csv", action="store_true",
                        help="Output raw CSV instead of the default markdown block")
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

    try:
        preset_default_i = get_start_interval_value(config)
    except ValueError as e:
        parser.error(str(e))

    start_interval = args.start_interval
    if start_interval is not None:
        logger.warning("Over-riding preset start mean %s with %s.", preset_default_i, start_interval)
    effective_i = start_interval if start_interval is not None else preset_default_i

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
        plateau_m, cache = find_ceiling(run_kwargs, args, progress, start_interval=start_interval)

        max_sample = min(plateau_m * 2, args.max_m)
        sample_points = log_spaced_integers(args.start_m, max_sample, args.samples)
        results = sample_at_points(run_kwargs, sample_points, cache, progress, plateau_m,
                                   start_interval=start_interval)

    # ----------------------------------------------------------------
    # Output
    # ----------------------------------------------------------------
    clock_arg = f" --clock-field {args.clock_field}" if args.clock_field else ""
    interval_arg = f" -i {start_interval}" if start_interval is not None else ""
    regen_cmd = f"python tools/bench_config_workers.py -c {args.config}{clock_arg}{interval_arg}"
    plateau_rows = cache.get(plateau_m, (None,))[0]

    print()

    if args.csv:
        writer = csv.DictWriter(
            sys.stdout, fieldnames=["w", "rows", "elapsed_s"], lineterminator="\n",
        )
        writer.writeheader()
        for r in results:
            writer.writerow({
                "w": r["m"], "rows": r["rows"], "elapsed_s": f"{r['elapsed_s']:.1f}",
            })
        plateau_rows_str = f"{plateau_rows:,} rows at plateau" if plateau_rows is not None else "rows unknown"
        err.print()
        err.print("[bold]── Empirical summary ──────────────────────────────────────[/bold]")
        err.print(f"  Empirical ceiling:  -w = [bold]{plateau_m:,}[/bold]  ({plateau_rows_str})")
        err.print(f"  Duration used:      {args.duration}  (seed={args.seed})")
        err.print(f"  To regenerate:      {regen_cmd}")
        err.print("[bold]────────────────────────────────────────────────────────────[/bold]")
    else:
        config_name = os.path.splitext(os.path.basename(args.config))[0]
        y_max = nice_ceil(plateau_rows) if plateau_rows else 1000

        x_vals = [str(r["m"]) for r in results]
        y_vals = [str(r["rows"]) for r in results]
        interval_desc = f"a start interval of {start_interval:g}" if start_interval is not None else "the preset's default start interval"
        # Little's Law (L = lambda*W) run in reverse: the empirical ceiling (L) and the
        # known start interval (1/lambda) together imply the average time a worker spends
        # busy per session (W) -- no separate measurement of the config's state machine
        # needed, since this is the same equation either direction.
        avg_busy_s = plateau_m * effective_i
        interval_label = "default " if start_interval is None else ""

        print(
            f"The {interval_label}start interval for workers in this preset is {effective_i:g}"
            f" seconds, with each worker busy for {avg_busy_s:g} seconds on average. The"
            f" maximum number of workers that can be busy at the same time is therefore"
            f" {avg_busy_s:g}/{effective_i:g} = {plateau_m:,}; increasing available workers"
            f" (using `-w`) without adjusting how often they begin work (using `-i`) has no"
            f" effect.\n"
            f"\n"
            f"The chart below shows how output scales with workers (varying `-w`) with"
            f" {interval_desc} (`--seed {args.seed}`, no schedule, {args.duration} simulated window)."
            f" To regenerate: `{regen_cmd}`.\n"
            f"\n"
            f"```mermaid\n"
            f"%%{{init: {{'themeVariables': {{'xyChart': {{'plotColorPalette': '{PLOT_COLOR}'}}}}}}}}%%\n"
            f"xychart-beta\n"
            f"    title \"{config_name} — rows vs -w ({args.duration}, seed={args.seed})\"\n"
            f"    x-axis \"-w\" [{', '.join(x_vals)}]\n"
            f"    y-axis \"Rows\" 0 --> {y_max}\n"
            f"    line [{', '.join(y_vals)}]\n"
            f"```"
        )


if __name__ == "__main__":
    main()
