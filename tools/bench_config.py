#!/usr/bin/env python3
"""Empirically measure how -m affects throughput, finding the concurrency ceiling.

Three-phase approach:
  1. Discovery: geometrically doubles -m from --start-m until row count plateaus.
  2. Refinement: binary-searches between the last non-plateau and first plateau value
     to pinpoint the ceiling precisely (within ~5%).
  3. Sampling: selects up to --samples evenly log-spaced -m values across
     [start_m, 2 × ceiling] and runs those for the final table.

Within each run the simulated clock is tracked by reading the clock field from output
lines, giving a real progress bar (% of simulated window elapsed) rather than a spinner.

If the config has an ambiguous clock field, pass --clock-field explicitly.

--compare-start-interval repeats the whole three-phase process three times — at the
preset's own event:start:timer interval, at half that interval (2x arrival rate), and
at double it (0.5x arrival rate) — using --start-interval on each generator.py
invocation. This both empirically checks that the -m ceiling scales linearly with
arrival rate (Little's Law: L = lambda*W, W independent of lambda) and produces a
three-series comparison chart for the preset doc.

Outputs CSV to stdout and an empirical summary (ceiling, regenerate command) to stderr.

Usage:
    python tools/bench_config.py -c presets/configs/vpc_flow_logs.json --clock-field start
    python tools/bench_config.py -c presets/configs/ecommerce.json --duration P1D
    python tools/bench_config.py -c presets/configs/ssh_auth.json --samples 6
    python tools/bench_config.py -c presets/configs/ecommerce.json --compare-start-interval
"""

import argparse
import csv
import json
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

DEFAULT_SEED = 42
DEFAULT_START = "2024-01-01T00:00:00"
DEFAULT_DURATION = "PT6H"
PLATEAU_THRESHOLD = 0.10
DEFAULT_MAX_M = 100_000
DEFAULT_SAMPLES = 10

# (multiplier, label, series description) — order fixed so chart line order is stable.
# A multiplier < 1 shortens the interval (faster arrivals, higher -m ceiling).
COMPARE_SERIES = [
    (0.5, "half", "1/2x interval (2x rate)"),
    (1.0, "default", "preset default"),
    (2.0, "double", "2x interval (0.5x rate)"),
]

# Mirrors generator.py's apply_start_interval_override dispatch — kept independent
# since bench_config.py treats generator.py as an opaque subprocess, not a library.
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
            f"--compare-start-interval does not support the event:start:timer state's "
            f"cardinality_distribution type '{dist_type}'. Supported types: "
            f"{sorted(MEAN_FIELD_BY_TYPE)}."
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
        f"-m={m}",
    ]
    if start_interval is not None:
        cmd.append(f"--start-interval={start_interval}")
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
    """True if curr_rows is within `threshold` of prev_rows, in EITHER direction.

    Must use abs() here: with a fixed seed but multiple worker threads sharing one
    RNG stream, changing -m changes thread-dispatch interleaving, which changes which
    random draws land on which session — so row counts aren't perfectly monotonic in
    -m. A plain (curr - prev) / prev < threshold treats any decrease as "plateaued"
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
# Phase 1 + 1b: discovery + binary-search refinement → one config's ceiling
# ---------------------------------------------------------------------------

def find_ceiling(run_kwargs, args, progress, label, start_interval=None):
    """Discover and refine the -m ceiling for one interval setting.

    Returns (plateau_m, cache) where cache maps m -> (rows, elapsed_s), reusable
    by the sampling phase.
    """
    prefix = f"[{label}] " if label else ""

    disc_task = progress.add_task(f"[cyan]{prefix}Phase 1 — discovery", total=None)

    cache = {}
    plateau_m = None
    prev_rows = None
    last_non_plateau_m = args.start_m
    m = args.start_m

    while m <= args.max_m:
        progress.update(disc_task, description=f"[cyan]{prefix}Phase 1 — discovery  -m {m:,}")
        run_task = progress.add_task(f"[dim]{prefix}disc  -m {m:>8,}", total=100.0)

        rows, elapsed = run_one(m=m, **run_kwargs, start_interval=start_interval,
                                progress=progress, run_task=run_task)
        cache[m] = (rows, elapsed)

        plat = is_plateau(prev_rows, rows, args.plateau_threshold)
        suffix = "  [yellow]← plateau[/yellow]" if plat else ""
        progress.update(
            run_task, completed=100.0,
            description=f"{prefix}disc  -m {m:>8,}  {rows:>10,} rows  {elapsed:.1f}s{suffix}",
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

    progress.update(disc_task, description=f"[cyan]{prefix}Phase 1 — complete")

    # Phase 1b: binary-search refinement — narrows the plateau boundary.
    # Doubling leaves up to a 2× gap. We bisect [last_non_plateau_m, plateau_m]
    # anchoring each comparison to the known-non-plateau rows so the
    # is_plateau check stays consistent.
    lo, hi = last_non_plateau_m, plateau_m
    lo_rows = cache[lo][0]

    if hi > lo + 1:
        refine_task = progress.add_task(
            f"[cyan]{prefix}Phase 1b — refining  [{lo:,} … {hi:,}]", total=None
        )
        while hi > lo + 1 and hi / lo > 1.05:
            mid = (lo + hi) // 2
            if mid == lo or mid == hi:
                break
            progress.update(
                refine_task,
                description=f"[cyan]{prefix}Phase 1b — refining  [{lo:,} … {hi:,}]  trying {mid:,}",
            )
            run_task = progress.add_task(f"[dim]{prefix}refine -m {mid:>8,}", total=100.0)
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
                description=f"{prefix}refine -m {mid:>8,}  {mid_rows:>10,} rows  {mid_elapsed:.1f}s{suffix}",
            )

        progress.update(
            refine_task,
            description=f"[cyan]{prefix}Phase 1b — complete  (ceiling ~{plateau_m:,})",
        )

    return plateau_m, cache


# ---------------------------------------------------------------------------
# Phase 2: sampling at a given set of -m points (reusing any cached runs)
# ---------------------------------------------------------------------------

def sample_at_points(run_kwargs, sample_points, cache, progress, label, plateau_m,
                     start_interval=None):
    prefix = f"[{label}] " if label else ""
    results = []

    sample_task = progress.add_task(
        f"[green]{prefix}Phase 2 — sampling  (plateau ~{plateau_m:,})",
        total=len(sample_points),
    )

    for m in sample_points:
        if m in cache:
            rows, elapsed = cache[m]
            run_task = progress.add_task(f"[dim]{prefix}sample-m {m:>8,}", total=100.0)
            progress.update(
                run_task, completed=100.0,
                description=f"{prefix}sample -m {m:>8,}  {rows:>10,} rows  (cached)",
            )
        else:
            run_task = progress.add_task(f"[dim]{prefix}sample -m {m:>8,}", total=100.0)
            rows, elapsed = run_one(m=m, **run_kwargs, start_interval=start_interval,
                                    progress=progress, run_task=run_task)
            progress.update(
                run_task, completed=100.0,
                description=f"{prefix}sample -m {m:>8,}  {rows:>10,} rows  {elapsed:.1f}s",
            )

        results.append({"m": m, "rows": rows, "elapsed_s": elapsed})
        progress.advance(sample_task, 1)

    progress.update(sample_task, description=f"[green]{prefix}Phase 2 — complete")
    return results


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

    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES,
                        help=f"Points in the final table. Default: {DEFAULT_SAMPLES}")
    parser.add_argument("--clock-field", default=None,
                        help="JSON field name carrying the simulated clock timestamp "
                             "(required if the config has multiple clock fields)")
    parser.add_argument("--csv", action="store_true",
                        help="Output raw CSV instead of the default markdown block")
    parser.add_argument("--compare-start-interval", action="store_true",
                        help="Repeat the benchmark at 1/2x and 2x the preset's own "
                             "event:start:timer interval, producing a three-series "
                             "comparison table/chart instead of the single-series default.")
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

    base_interval = None
    if args.compare_start_interval:
        try:
            base_interval = get_start_interval_value(config)
        except ValueError as e:
            parser.error(str(e))

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

    series_defs = COMPARE_SERIES if args.compare_start_interval else [(1.0, None, None)]

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
        # Phase 1/1b per series — independent ceiling discovery
        # ----------------------------------------------------------------
        ceilings = {}   # label -> (plateau_m, cache, start_interval)
        for multiplier, label, _desc in series_defs:
            start_interval = None if base_interval is None else base_interval * multiplier
            plateau_m, cache = find_ceiling(
                run_kwargs, args, progress, label, start_interval=start_interval
            )
            ceilings[label] = (plateau_m, cache, start_interval)

        # ----------------------------------------------------------------
        # Phase 2 — shared sample points across all series, so line series
        # in the comparison chart share one x-axis
        # ----------------------------------------------------------------
        max_ceiling = max(plateau_m for plateau_m, _, _ in ceilings.values())
        max_sample = min(max_ceiling * 2, args.max_m)
        sample_points = log_spaced_integers(args.start_m, max_sample, args.samples)

        series_results = {}  # label -> list of {"m", "rows", "elapsed_s"}
        for multiplier, label, _desc in series_defs:
            plateau_m, cache, start_interval = ceilings[label]
            series_results[label] = sample_at_points(
                run_kwargs, sample_points, cache, progress, label, plateau_m,
                start_interval=start_interval,
            )

    # ----------------------------------------------------------------
    # Output
    # ----------------------------------------------------------------
    clock_arg = f" --clock-field {args.clock_field}" if args.clock_field else ""

    if not args.compare_start_interval:
        default_plateau_m, default_cache, _ = ceilings[None]
        results = series_results[None]
        plateau_rows = default_cache.get(default_plateau_m, (None,))[0]
        regen_cmd = f"python tools/bench_config.py -c {args.config}{clock_arg}"

        print()

        if args.csv:
            writer = csv.DictWriter(
                sys.stdout, fieldnames=["m", "rows", "elapsed_s"], lineterminator="\n",
            )
            writer.writeheader()
            for r in results:
                writer.writerow({
                    "m": r["m"], "rows": r["rows"], "elapsed_s": f"{r['elapsed_s']:.1f}",
                })
            plateau_rows_str = f"{plateau_rows:,} rows at plateau" if plateau_rows is not None else "rows unknown"
            err.print()
            err.print("[bold]── Empirical summary ──────────────────────────────────────[/bold]")
            err.print(f"  Empirical ceiling:  -m = [bold]{default_plateau_m:,}[/bold]  ({plateau_rows_str})")
            err.print(f"  Duration used:      {args.duration}  (seed={args.seed})")
            err.print(f"  To regenerate:      {regen_cmd}")
            err.print("[bold]────────────────────────────────────────────────────────────[/bold]")
        else:
            config_name = os.path.splitext(os.path.basename(args.config))[0]
            y_max = nice_ceil(plateau_rows) if plateau_rows else 1000

            x_vals = [str(r["m"]) for r in results]
            y_vals = [str(r["rows"]) for r in results]

            table_rows = "\n".join(
                f"| {r['m']:,} | {r['rows']:,} | {r['elapsed_s']:.1f} |"
                for r in results
            )

            print(
                f"The `-m` ceiling is ~{default_plateau_m:,}. Setting `-m` above this has no effect"
                f" — the worker pool is never fully used.\n"
                f"\n"
                f"The table below shows how output scales with `-m` (`--seed {args.seed}`,"
                f" no schedule, {args.duration} simulated window)."
                f" To regenerate: `{regen_cmd}`.\n"
                f"\n"
                f"| `-m` | Rows ({args.duration}) | Wall-clock (s) |\n"
                f"| ---: | ---: | ---: |\n"
                f"{table_rows}\n"
                f"\n"
                f"```mermaid\n"
                f"xychart-beta\n"
                f"    title \"{config_name} — rows vs -m ({args.duration}, seed={args.seed})\"\n"
                f"    x-axis [{', '.join(x_vals)}]\n"
                f"    y-axis \"Rows\" 0 --> {y_max}\n"
                f"    line [{', '.join(y_vals)}]\n"
                f"```"
            )
        return

    # --- --compare-start-interval output ---
    regen_cmd = f"python tools/bench_config.py -c {args.config} --compare-start-interval{clock_arg}"
    config_name = os.path.splitext(os.path.basename(args.config))[0]

    default_plateau_m = ceilings["default"][0]
    half_plateau_m = ceilings["half"][0]
    double_plateau_m = ceilings["double"][0]

    print()

    if args.csv:
        writer = csv.DictWriter(
            sys.stdout,
            fieldnames=["m", "rows_half", "rows_default", "rows_double"],
            lineterminator="\n",
        )
        writer.writeheader()
        for i, m in enumerate(sample_points):
            writer.writerow({
                "m": m,
                "rows_half": series_results["half"][i]["rows"],
                "rows_default": series_results["default"][i]["rows"],
                "rows_double": series_results["double"][i]["rows"],
            })
        err.print()
        err.print("[bold]── Empirical summary (--compare-start-interval) ────────────[/bold]")
        err.print(f"  1/2x interval ceiling:  -m = [bold]{half_plateau_m:,}[/bold]")
        err.print(f"  Default ceiling:        -m = [bold]{default_plateau_m:,}[/bold]")
        err.print(f"  2x interval ceiling:    -m = [bold]{double_plateau_m:,}[/bold]")
        err.print(f"  Duration used:          {args.duration}  (seed={args.seed})")
        err.print(f"  To regenerate:          {regen_cmd}")
        err.print("[bold]─────────────────────────────────────────────────────────────[/bold]")
    else:
        table_rows = "\n".join(
            f"| {m:,} | {series_results['half'][i]['rows']:,} "
            f"| {series_results['default'][i]['rows']:,} "
            f"| {series_results['double'][i]['rows']:,} |"
            for i, m in enumerate(sample_points)
        )

        all_rows = [r["rows"] for results in series_results.values() for r in results]
        y_max = nice_ceil(max(all_rows)) if all_rows else 1000
        x_vals = [str(m) for m in sample_points]

        ratio_half = half_plateau_m / default_plateau_m if default_plateau_m else float("nan")
        ratio_double = double_plateau_m / default_plateau_m if default_plateau_m else float("nan")

        print(
            f"The `-m` ceiling at the preset's default interarrival interval is ~{default_plateau_m:,}."
            f" Halving the interval (2x arrival rate) raises it to ~{half_plateau_m:,} ({ratio_half:.2f}x);"
            f" doubling the interval (0.5x arrival rate) lowers it to ~{double_plateau_m:,} ({ratio_double:.2f}x)."
            f" The ceiling scales with arrival rate.\n"
            f"\n"
            f"The table below shows how output scales with `-m` at each interval"
            f" (`--seed {args.seed}`, no schedule, {args.duration} simulated window)."
            f" To regenerate: `{regen_cmd}`.\n"
            f"\n"
            f"| `-m` | Rows — 1/2x interval | Rows — default | Rows — 2x interval |\n"
            f"| ---: | ---: | ---: | ---: |\n"
            f"{table_rows}\n"
            f"\n"
            f"```mermaid\n"
            f"xychart-beta\n"
            f"    title \"{config_name} — rows vs -m by interarrival interval ({args.duration}, seed={args.seed})\"\n"
            f"    x-axis [{', '.join(x_vals)}]\n"
            f"    y-axis \"Rows\" 0 --> {y_max}\n"
            f"    line [{', '.join(str(r['rows']) for r in series_results['half'])}]\n"
            f"    line [{', '.join(str(r['rows']) for r in series_results['default'])}]\n"
            f"    line [{', '.join(str(r['rows']) for r in series_results['double'])}]\n"
            f"```"
        )


if __name__ == "__main__":
    main()
