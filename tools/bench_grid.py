#!/usr/bin/env python3
"""Sweep a 2D grid of -w x -i, recording volume, crash, or timeout at each cell.

This is a coarse illustration, not a precision tool -- for a trustworthy exact
boundary on a single axis, use bench_config_workers.py (-w ceiling at a given
-i) or bench_config_interval.py (-i floor at a given -w), which do continuous
discovery+refine rather than reading a fixed grid. Both axes here are fixed,
static lists meant to be reused across presets without per-profile tuning, not
computed per run -- see log_space()/linear_space() below if a custom scale is
ever needed instead.

Rows (-i) are visited slowest-first (largest -i to smallest) -- the cheapest,
safest cell first, the most expensive/riskiest last. Within a row, -w is
scanned ascending as before. Two independent plateau checks skip cells rather
than running them, both requiring two consecutive matching readings (a single
match can be noise -- e.g. 53 vs 54 rows satisfies a 10% relative threshold
purely because the absolute count is small, despite the curve still genuinely
climbing):

  - Row-wise (the original check): once two consecutive -w values in a row
    give the same volume, every larger -w in that row is known to match too
    -- Little's Law says more workers than the ceiling changes nothing.
  - Column-wise (new): once two rows (any two processed so far, not
    necessarily adjacent) give the same volume at a given -w, that -w has
    hit its floor -- every row processed from here on is faster (smaller -i,
    visited later in the slowest-first order), and a fixed worker count that
    has already stopped responding to speed increases won't start responding
    to even faster ones. So that column is skipped outright for every
    remaining row, backfilled with the confirmed value.

The two checks are complementary, not redundant: they're the same underlying
w*i saturation curve read from its two different axes, and a coarse fixed
grid can have gaps big enough for one axis's check to miss a transition the
other axis would have caught (confirmed on this preset's own -w 25 column,
where three grid points -i 0.01/0.1/1 all landed on the same plateau while
the row-wise check alone -- which never looks across rows -- had no way to
notice).

A crash or a cell exceeding --cell-timeout stops that row's own -w ascent
(every larger -w in that row is assumed at least as bad) but does NOT
propagate across rows -- a crash at fast -i says nothing about a slower row's
risk at the same -w, since risk here tracks worker count, not arrival rate.

Contention near the OS thread-creation limit gets worse than linearly with
-w well before it actually fails outright, so a cell can take minutes without
crashing. Each cell therefore runs under a wall-clock budget (--cell-timeout,
default 600s): if it's not done in time, it's killed and treated like a crash
for that row's purposes (not a data-volume result). Progress is logged live --
a heartbeat line every 10s of elapsed time while a cell runs, plus a result
line when it finishes -- specifically so a slow cell doesn't look identical
to a hung one.

Output is a markdown table with -i as rows and -w as columns, each cell
colored by volume (log-scale quartile of the completed results, green=low to
red=high), or marked with a symbol (crashed/timed-out/plateau-skipped)
explaining why no measurement is shown.

Usage:
    python tools/bench_grid.py -c presets/configs/pbx_calls.json
    python tools/bench_grid.py -c presets/configs/pbx_calls.json \
        --w-values 1,10,100,1000,10000 --i-values 0.1,1,10 --cell-timeout 60
"""

import argparse
import json
import logging
import math
import signal
import subprocess
import sys
import threading
import time

# Python doesn't run cleanup code on SIGTERM by default, so killing this script
# (e.g. because a cell is hung) would otherwise orphan its in-flight generator.py
# child, which keeps running indefinitely -- this happened in practice while
# building this tool. Track whatever's currently running and kill it too.
_current_proc = [None]


def _kill_current_and_exit(signum, frame):
    proc = _current_proc[0]
    if proc is not None and proc.poll() is None:
        logging.warning("Received termination signal -- killing in-flight generator.py process")
        proc.kill()
    sys.exit(1)


signal.signal(signal.SIGTERM, _kill_current_and_exit)
signal.signal(signal.SIGINT, _kill_current_and_exit)

DEFAULT_SEED = 42
DEFAULT_START = "2024-01-01T00:00:00"
DEFAULT_DURATION = "PT6H"
PLATEAU_THRESHOLD = 0.10
DEFAULT_CELL_TIMEOUT = 600.0

# Fixed, not computed -- a generic grid meant to be reused across presets without
# per-profile tuning. See log_space()/linear_space() below if a custom scale is
# ever needed instead. 10000 (the hard -w cap) is deliberately left out of the
# default grid; pass --w-values explicitly to probe that far.
DEFAULT_W_VALUES = [1, 5, 25, 100, 250, 1000, 2500, 5000]

# The fixed part of the -i default grid. main() adds the config's own configured
# event:start:timer mean to this list (sorted in) unless --i-values is given
# explicitly -- otherwise the default grid would never actually illustrate the
# preset's own out-of-the-box behavior, only hypothetical faster rates.
BASE_I_VALUES = [0.01, 0.1, 1.0]

# Volume tiers, low to high (log-scale quartiles of completed results).
TIERS = ["🟩", "🟨", "🟧", "🟥"]
CRASH_MARK = "💥"
TIMEOUT_MARK = "⏱️"
PLATEAU_MARK = "🟰"  # skipped -- row-wise or column-wise plateau already confirms this would match


def log_space(lo, hi, n):
    """n values geometrically spaced from lo to hi inclusive (even ratio, not hand-picked)."""
    if n <= 1:
        return [lo]
    ratio = (hi / lo) ** (1 / (n - 1))
    return [lo * (ratio ** k) for k in range(n)]


def linear_space(lo, hi, n):
    """n values at even steps of hi/(n-1), starting from 0 -- not from lo -- so
    points land on clean round numbers (e.g. multiples of 1250) rather than being
    offset by lo. Only the first point is clamped up to lo (0 itself usually isn't
    a valid -w/-i)."""
    if n <= 1:
        return [lo]
    step = hi / (n - 1)
    values = [step * k for k in range(n)]
    values[0] = lo
    return values


def is_plateau(prev_rows, curr_rows, threshold):
    """Same check as bench_config_workers.py: abs() because thread-interleaving
    noise under a fixed seed can make row counts dip as well as rise."""
    if prev_rows is None or prev_rows == 0:
        return curr_rows == 0
    return abs(curr_rows - prev_rows) / prev_rows < threshold


def plateau_streak_step(prev_rows, rows, streak, threshold):
    """Advance a plateau-confirmation streak by one reading. Normally requires two
    consecutive within-threshold matches, not one -- a single near-match can be pure
    noise when absolute counts are small. But an EXACT match (not just within
    threshold) confirms immediately: once truly past a ceiling/floor there's no
    worker contention left, so output for a fixed seed is fully deterministic --
    bit-for-bit identical on every probe, not just close -- which is categorically
    stronger evidence than a within-threshold match and was never what the
    two-reading requirement was guarding against."""
    if prev_rows is not None and rows == prev_rows:
        return 2
    if prev_rows is not None and is_plateau(prev_rows, rows, threshold):
        return streak + 1
    return 0


def make_heartbeat(label, throttle=10.0):
    """Log a liveness line every `throttle` seconds of elapsed time. run_cell polls
    every 1s internally for timeout accuracy, but logging that often would be noise."""
    state = {"last": None}

    def heartbeat(elapsed, rows_so_far):
        if state["last"] is None or elapsed < state["last"] or elapsed - state["last"] >= throttle:
            state["last"] = elapsed
            logging.info(f"{label}  ... still running, {rows_so_far:,} rows so far ({elapsed:.0f}s)")
    return heartbeat


def run_cell(config_path, w, i, duration_str, start_str, seed, cell_timeout, on_heartbeat=None):
    """Run one generator.py invocation. Drains stdout in a background thread while
    polling for completion -- without this, a cell whose output exceeds the OS pipe
    buffer (easily happens here: outputs regularly exceed 100k lines) would deadlock
    the child on its own write() call, which would look identical to a genuinely slow
    cell but for an unrelated reason.

    Returns (rows, status, elapsed) where status is 'ok', 'crashed', or 'timeout'.
    """
    cmd = [
        sys.executable, "-u", "generator.py",
        "-c", config_path,
        "-r", duration_str,
        "-s", start_str,
        f"--seed={seed}",
        f"-w={w}",
        f"-i={i}",
    ]
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    _current_proc[0] = proc

    row_count = [0]

    def drain_stdout():
        for line in proc.stdout:
            if line.strip():
                row_count[0] += 1

    reader = threading.Thread(target=drain_stdout, daemon=True)
    reader.start()

    timed_out = False
    try:
        while True:
            try:
                proc.wait(timeout=1.0)
                break
            except subprocess.TimeoutExpired:
                elapsed = time.perf_counter() - t0
                if on_heartbeat is not None:
                    on_heartbeat(elapsed, row_count[0])
                if elapsed >= cell_timeout:
                    timed_out = True
                    proc.kill()
                    proc.wait()
                    break
    finally:
        _current_proc[0] = None
    reader.join(timeout=2)
    elapsed = time.perf_counter() - t0

    if timed_out:
        return row_count[0], "timeout", elapsed
    return row_count[0], ("crashed" if proc.returncode != 0 else "ok"), elapsed


def fmt_i(i):
    return f"{i:g}"


def parse_float_list(s):
    return [float(x) for x in s.split(",")]


def get_config_mean_interval(config_path):
    """Read the event:start:timer state's own configured interarrival period --
    same per-distribution-type field mapping as generator.py's
    apply_start_interval_override, just reading instead of overriding. Returns
    None if the config has no event:start:timer state or uses a distribution
    type with no single central-tendency field (e.g. 'uniform')."""
    with open(config_path) as f:
        config = json.load(f)
    timer_state = next((s for s in config.get("states", []) if s.get("type") == "event:start:timer"), None)
    if timer_state is None:
        return None
    dist = timer_state.get("cardinality_distribution", {})
    field = {"constant": "value", "exponential": "mean", "normal": "mean", "gmm_temporal": "mean"}.get(dist.get("type"))
    return dist.get(field) if field else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", required=True, help="Path to generator config JSON")
    parser.add_argument("--w-values", type=parse_float_list, default=DEFAULT_W_VALUES,
                        help=f"Comma-separated -w grid. Default: {','.join(map(str, DEFAULT_W_VALUES))}")
    parser.add_argument("--i-values", type=parse_float_list, default=None,
                        help=f"Comma-separated -i grid. Default: {','.join(map(str, BASE_I_VALUES))}, "
                             f"plus the config's own event:start:timer mean.")
    parser.add_argument("--plateau-threshold", type=float, default=PLATEAU_THRESHOLD)
    parser.add_argument("--cell-timeout", type=float, default=DEFAULT_CELL_TIMEOUT,
                        help=f"Per-cell wall-clock budget in seconds. Default: {DEFAULT_CELL_TIMEOUT}")
    parser.add_argument("--duration", default=DEFAULT_DURATION, help=f"Simulated window. Default: {DEFAULT_DURATION}")
    parser.add_argument("--start", default=DEFAULT_START, help=f"Simulated start time. Default: {DEFAULT_START}")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Random seed. Default: {DEFAULT_SEED}")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S", stream=sys.stderr)

    w_values = sorted(set(round(w) for w in args.w_values))
    config_mean = get_config_mean_interval(args.config)
    if args.i_values is None:
        if config_mean is None:
            logging.warning("Could not read the config's own event:start:timer mean -- "
                             "defaulting -i grid to %s only.", BASE_I_VALUES)
            i_values = sorted(BASE_I_VALUES)
        else:
            i_values = sorted(set(BASE_I_VALUES) | {config_mean})
    else:
        i_values = sorted(args.i_values)

    total_cells = len(w_values) * len(i_values)
    # cell_info[(w, i)] = (rows, status) where status is "ok", "crashed", "timeout",
    # "row-plateau", or "column-plateau" -- the last two are skips, not measurements,
    # but carry the confirmed value anyway (row-plateau's is never displayed; column-
    # plateau's is, since unlike a row skip it wasn't independently re-verified but
    # is still real, useful information for tier coloring).
    cell_info = {}

    # Column state, threaded across rows (processed slowest -i to fastest -- see
    # module docstring): once two rows agree at a given -w, every row from here on
    # is faster and gets that -w skipped outright.
    col_state = {w: {"prev": None, "streak": 0, "confirmed": None} for w in w_values}

    task_n = 0
    ran = 0
    for i in sorted(i_values, reverse=True):
        prev_rows = None
        row_streak = 0
        stopped = False
        stop_status = None  # "crashed" or "timeout"
        for w in w_values:
            task_n += 1
            label = f"-i {fmt_i(i):<6} -w {w:<6,}"

            if stopped:
                cell_info[(w, i)] = (0, "row-plateau" if stop_status is None else stop_status)
                logging.info(f"[{task_n}/{total_cells}] {label}  skipped (row {stop_status or 'plateau'})")
                continue

            confirmed = col_state[w]["confirmed"]
            if confirmed is not None:
                cell_info[(w, i)] = (confirmed, "column-plateau")
                logging.info(f"[{task_n}/{total_cells}] {label}  skipped (column plateau, {confirmed:,} rows)")
                # Feed the inferred value into the row's own bookkeeping too, so a
                # row entirely covered by already-confirmed columns still triggers
                # its own plateau stop instead of running out the rest for real.
                row_streak = plateau_streak_step(prev_rows, confirmed, row_streak, args.plateau_threshold)
                if row_streak >= 2:
                    stopped, stop_status = True, None
                prev_rows = confirmed
                continue

            logging.info(f"[{task_n}/{total_cells}] {label}  running...")
            rows, status, elapsed = run_cell(
                args.config, w, i, args.duration, args.start, args.seed,
                args.cell_timeout, on_heartbeat=make_heartbeat(label),
            )
            cell_info[(w, i)] = (rows, status)
            ran += 1
            status_text = {"ok": f"{rows:,} rows", "crashed": "CRASHED", "timeout": f"TIMED OUT ({rows:,} rows so far)"}[status]
            logging.info(f"[{task_n}/{total_cells}] {label}  {status_text}  ({elapsed:.1f}s)")

            if status in ("crashed", "timeout"):
                stopped, stop_status = True, status
                continue

            row_streak = plateau_streak_step(prev_rows, rows, row_streak, args.plateau_threshold)
            if row_streak >= 2:
                stopped, stop_status = True, None
            prev_rows = rows

            cs = col_state[w]
            cs["streak"] = plateau_streak_step(cs["prev"], rows, cs["streak"], args.plateau_threshold)
            if cs["streak"] >= 2:
                cs["confirmed"] = rows
            cs["prev"] = rows

    logging.info(f"Ran {ran} of {total_cells} cells ({total_cells - ran} skipped by plateau/crash/timeout detection).")

    # --- Color tiers from completed results (log-scale quartiles) ---
    ok_rows = sorted(rows for (rows, status) in cell_info.values() if status in ("ok", "column-plateau") and rows > 0)

    def tier_for(rows):
        if not ok_rows or rows <= 0:
            return TIERS[0]
        log_rows = math.log(rows)
        log_vals = [math.log(r) for r in ok_rows]
        lo, hi = log_vals[0], log_vals[-1]
        if hi == lo:
            return TIERS[-1]
        frac = (log_rows - lo) / (hi - lo)
        idx = min(int(frac * len(TIERS)), len(TIERS) - 1)
        return TIERS[idx]

    # --- Render markdown table: rows = -i, columns = -w ---
    header = ("| `-i` \\ `-w` | " + " | ".join(f"{w:,}" for w in w_values) + " |")
    sep = "| :--- | " + " | ".join(":---" for _ in w_values) + " |"
    lines = [header, sep]
    for i in i_values:
        cells = []
        for w in w_values:
            rows, status = cell_info[(w, i)]
            if status == "crashed":
                cells.append(CRASH_MARK)
            elif status == "timeout":
                cells.append(TIMEOUT_MARK)
            elif status in ("row-plateau", "column-plateau"):
                cells.append(PLATEAU_MARK if status == "row-plateau" else f"{PLATEAU_MARK} {rows:,}")
            else:
                cells.append(f"{tier_for(rows)} {rows:,}")
        row_label = fmt_i(i) + (" (default)" if config_mean is not None and i == config_mean else "")
        lines.append(f"| {row_label} | " + " | ".join(cells) + " |")

    print()
    print(f"Grid: {len(w_values)} × {len(i_values)} = {total_cells} cells ({ran} run, {total_cells - ran} skipped), "
          f"`--seed {args.seed}`, {args.duration} simulated window, {args.cell_timeout:.0f}s per-cell timeout.")
    print()
    print("\n".join(lines))
    print()
    print(f"{CRASH_MARK} = thread-creation limit hit. "
          f"{TIMEOUT_MARK} = Timeout. "
          f"{PLATEAU_MARK} = Plateau (row-wise skip, or column-wise skip with its confirmed value shown).")


if __name__ == "__main__":
    main()
