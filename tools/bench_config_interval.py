#!/usr/bin/env python3
"""Empirically measure how -i (interarrival period) affects throughput, finding the
-i floor at a given -w -- the slowest -i beyond which the worker pool, not arrival
rate, is the bottleneck.

Three-phase approach (mirrors bench_config_workers.py's -w ceiling search, just on
the other axis and in the opposite direction -- -w's useful direction is up, hence
'ceiling'; -i's is down, hence 'floor'):
  1. Discovery: geometrically halves -i from --start-i until row count plateaus.
  2. Refinement: bisects (geometrically -- -i spans orders of magnitude, unlike -w's
     integer count) between the last non-plateau and first plateau value to pinpoint
     the floor precisely (within ~5%).
  3. Sampling: selects up to --samples evenly log-spaced -i values across
     [floor / 2, --start-i] and runs those for the final table.

Within each run the simulated clock is tracked by reading the clock field from output
lines, giving a real progress bar (% of simulated window elapsed) rather than a spinner.

If the config has an ambiguous clock field, pass --clock-field explicitly.

-w has no equivalent to bench_config_workers.py's config-derived -i default -- a
config doesn't specify a worker count -- so -w is required here.

Outputs CSV to stdout and an empirical summary (floor, regenerate command) to stderr.

Usage:
    python tools/bench_config_interval.py -c presets/configs/pbx_calls.json -w 25
    python tools/bench_config_interval.py -c presets/configs/vpc_flow_logs.json -w 66 --clock-field start
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
DEFAULT_START_I = 1000.0
DEFAULT_MIN_I = 0.0001
DEFAULT_SAMPLES = 10
PLOT_COLOR = "#2563eb"  # xychart-beta's default single-series line color is a pale
# theme-dependent blue/grey that's low-contrast in most renderers (VS Code's preview
# included) -- overridden via plotColorPalette rather than relying on the theme.


# ---------------------------------------------------------------------------
# Clock field detection -- identical to bench_config_workers.py
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
    direct = []
    for emitter in config.get("emitters", []):
        for dim in emitter.get("dimensions", []):
            if dim.get("type") == "clock" and dim["name"] not in direct:
                direct.append(dim["name"])
    if direct:
        return (direct[0], []) if len(direct) == 1 else (None, direct)

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

def run_one(config_path, w, i, duration_str, start_str, seed,
            clock_field, start_dt, end_dt, progress, run_task):
    """Run one generator invocation, streaming output for live progress."""
    cmd = [
        sys.executable, "generator.py",
        "-c", config_path,
        "-r", duration_str,
        "-s", start_str,
        f"--seed={seed}",
        f"-w={w}",
        f"-i={i}",
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
            raise RuntimeError(f"generator.py exited non-zero for -i {i}")

    elapsed_wall = time.perf_counter() - t0
    progress.update(run_task, completed=100.0)
    return row_count, elapsed_wall


# ---------------------------------------------------------------------------
# Plateau detection / sample-point generation
# ---------------------------------------------------------------------------

def is_plateau(prev_rows, curr_rows, threshold):
    """Same abs()-based check as bench_config_workers.py / bench_grid.py, for the
    same reason: thread-interleaving noise under a fixed seed can make row counts
    dip as well as rise between -i values, not just monotonically climb."""
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


def log_spaced_floats(lo, hi, n):
    """Up to n distinct floats, log-spaced from lo to hi inclusive. Float
    counterpart of bench_config_workers.py's log_spaced_integers -- -i is a
    continuous period, not an integer worker count."""
    if lo >= hi or n <= 1:
        return [lo] if lo <= hi else [hi]
    log_lo, log_hi = math.log(lo), math.log(hi)
    pts = set()
    for k in range(n):
        t = k / (n - 1)
        v = math.exp(log_lo + t * (log_hi - log_lo))
        pts.add(max(lo, min(hi, v)))
    return sorted(pts)


# ---------------------------------------------------------------------------
# Phase 1 + 1b: discovery + binary-search refinement → the -i floor
# ---------------------------------------------------------------------------

def find_floor(run_kwargs, args, progress):
    """Discover and refine the -i floor at the given -w.

    Returns (plateau_i, cache) where cache maps i -> (rows, elapsed_s), reusable
    by the sampling phase.
    """
    disc_task = progress.add_task("[cyan]Phase 1 — discovery", total=None)

    cache = {}
    plateau_i = None
    prev_rows = None
    last_non_plateau_i = args.start_i
    i = args.start_i

    while i >= args.min_i:
        progress.update(disc_task, description=f"[cyan]Phase 1 — discovery  -i {i:g}")
        run_task = progress.add_task(f"[dim]disc  -i {i:>10g}", total=100.0)

        rows, elapsed = run_one(i=i, **run_kwargs, progress=progress, run_task=run_task)
        cache[i] = (rows, elapsed)

        plat = is_plateau(prev_rows, rows, args.plateau_threshold)
        suffix = "  [yellow]← plateau[/yellow]" if plat else ""
        progress.update(
            run_task, completed=100.0,
            description=f"disc  -i {i:>10g}  {rows:>10,} rows  {elapsed:.1f}s{suffix}",
        )

        if plat:
            plateau_i = i
            break
        else:
            last_non_plateau_i = i

        prev_rows = rows
        next_i = i / 2
        if next_i < args.min_i:
            break
        i = next_i

    if plateau_i is None:
        plateau_i = i

    progress.update(disc_task, description="[cyan]Phase 1 — complete")

    # Phase 1b: geometric bisection refine -- multiplicative midpoint since -i spans
    # orders of magnitude, unlike -w's integer count. Anchored to the known-non-
    # plateau (slow) rows so the is_plateau check stays consistent, same as
    # bench_config_workers.py's refine anchors to the known-non-plateau -w rows.
    i_lo, i_hi = plateau_i, last_non_plateau_i
    hi_rows = cache[i_hi][0]

    if i_hi > i_lo * 1.05:
        refine_task = progress.add_task(
            f"[cyan]Phase 1b — refining  [{i_lo:g} … {i_hi:g}]", total=None
        )
        while i_hi > i_lo * 1.05:
            mid = (i_lo * i_hi) ** 0.5
            progress.update(
                refine_task,
                description=f"[cyan]Phase 1b — refining  [{i_lo:g} … {i_hi:g}]  trying {mid:g}",
            )
            run_task = progress.add_task(f"[dim]refine -i {mid:>10g}", total=100.0)
            mid_rows, mid_elapsed = run_one(i=mid, **run_kwargs, progress=progress, run_task=run_task)
            cache[mid] = (mid_rows, mid_elapsed)

            if is_plateau(hi_rows, mid_rows, args.plateau_threshold):
                i_hi, plateau_i = mid, mid
                hi_rows = mid_rows
                suffix = "  [yellow]← plateau[/yellow]"
            else:
                i_lo = mid
                suffix = ""
            progress.update(
                run_task, completed=100.0,
                description=f"refine -i {mid:>10g}  {mid_rows:>10,} rows  {mid_elapsed:.1f}s{suffix}",
            )

        progress.update(
            refine_task,
            description=f"[cyan]Phase 1b — complete  (floor ~{plateau_i:g})",
        )

    return plateau_i, cache


# ---------------------------------------------------------------------------
# Phase 2: sampling at a given set of -i points (reusing any cached runs)
# ---------------------------------------------------------------------------

def sample_at_points(run_kwargs, sample_points, cache, progress, plateau_i):
    results = []

    sample_task = progress.add_task(
        f"[green]Phase 2 — sampling  (floor ~{plateau_i:g})",
        total=len(sample_points),
    )

    for i in sample_points:
        if i in cache:
            rows, elapsed = cache[i]
            run_task = progress.add_task(f"[dim]sample-i {i:>10g}", total=100.0)
            progress.update(
                run_task, completed=100.0,
                description=f"sample -i {i:>10g}  {rows:>10,} rows  (cached)",
            )
        else:
            run_task = progress.add_task(f"[dim]sample -i {i:>10g}", total=100.0)
            rows, elapsed = run_one(i=i, **run_kwargs, progress=progress, run_task=run_task)
            progress.update(
                run_task, completed=100.0,
                description=f"sample -i {i:>10g}  {rows:>10,} rows  {elapsed:.1f}s",
            )

        results.append({"i": i, "rows": rows, "elapsed_s": elapsed})
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
    parser.add_argument("-w", dest="workers", type=int, required=True,
                        help="Worker count to find the -i floor for. Required -- unlike -i "
                             "in bench_config_workers.py, a config has no -w of its own to "
                             "default to.")
    parser.add_argument("--duration", default=DEFAULT_DURATION,
                        help=f"Simulated window (ISO 8601 duration). Default: {DEFAULT_DURATION}")
    parser.add_argument("--start", default=DEFAULT_START,
                        help=f"Simulated start time (ISO 8601). Default: {DEFAULT_START}")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"Random seed. Default: {DEFAULT_SEED}")
    parser.add_argument("--start-i", type=float, default=DEFAULT_START_I,
                        help=f"Slowest (largest) -i value to test. Default: {DEFAULT_START_I}")
    parser.add_argument("--min-i", type=float, default=DEFAULT_MIN_I,
                        help=f"Lower bound on -i during discovery. Default: {DEFAULT_MIN_I}")
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

    start_dt = dateutil.parser.isoparse(args.start)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    end_dt = start_dt + isodate.parse_duration(args.duration)

    run_kwargs = dict(
        config_path=args.config,
        w=args.workers,
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
        plateau_i, cache = find_floor(run_kwargs, args, progress)

        min_sample = max(args.min_i, plateau_i / 2)
        sample_points = log_spaced_floats(min_sample, args.start_i, args.samples)
        results = sample_at_points(run_kwargs, sample_points, cache, progress, plateau_i)

    # ----------------------------------------------------------------
    # Output
    # ----------------------------------------------------------------
    clock_arg = f" --clock-field {args.clock_field}" if args.clock_field else ""
    regen_cmd = f"python tools/bench_config_interval.py -c {args.config} -w {args.workers}{clock_arg}"
    plateau_rows = cache.get(plateau_i, (None,))[0]

    print()

    if args.csv:
        writer = csv.DictWriter(
            sys.stdout, fieldnames=["i", "rows", "elapsed_s"], lineterminator="\n",
        )
        writer.writeheader()
        for r in results:
            writer.writerow({
                "i": f"{r['i']:g}", "rows": r["rows"], "elapsed_s": f"{r['elapsed_s']:.1f}",
            })
        plateau_rows_str = f"{plateau_rows:,} rows at plateau" if plateau_rows is not None else "rows unknown"
        err.print()
        err.print("[bold]── Empirical summary ──────────────────────────────────────[/bold]")
        err.print(f"  Empirical floor:    -i = [bold]{plateau_i:g}[/bold]  ({plateau_rows_str}, at -w {args.workers})")
        err.print(f"  Duration used:      {args.duration}  (seed={args.seed})")
        err.print(f"  To regenerate:      {regen_cmd}")
        err.print("[bold]────────────────────────────────────────────────────────────[/bold]")
    else:
        config_name = os.path.splitext(os.path.basename(args.config))[0]
        y_max = nice_ceil(plateau_rows) if plateau_rows else 1000

        x_vals = [f"{r['i']:g}" for r in results]
        y_vals = [str(r["rows"]) for r in results]

        print(
            f"The `-i` floor at `-w {args.workers}` is ~{plateau_i:g}. Setting `-i` below this"
            f" has no effect — the worker pool, not arrival rate, is already the bottleneck.\n"
            f"\n"
            f"The chart below shows how output scales with `-i` at `-w {args.workers}`"
            f" (`--seed {args.seed}`, no schedule, {args.duration} simulated window)."
            f" To regenerate: `{regen_cmd}`.\n"
            f"\n"
            f"```mermaid\n"
            f"%%{{init: {{'themeVariables': {{'xyChart': {{'plotColorPalette': '{PLOT_COLOR}'}}}}}}}}%%\n"
            f"xychart-beta\n"
            f"    title \"{config_name} — rows vs -i at -w {args.workers} ({args.duration}, seed={args.seed})\"\n"
            f"    x-axis \"-i\" [{', '.join(x_vals)}]\n"
            f"    y-axis \"Rows\" 0 --> {y_max}\n"
            f"    line [{', '.join(y_vals)}]\n"
            f"```"
        )


if __name__ == "__main__":
    main()
