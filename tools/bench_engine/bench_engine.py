#!/usr/bin/env python3
"""Measure the engine's speed and memory use, and compare against a baseline.

Runs each workload several times as a separate generator.py process, with a fixed
seed and the simulated clock, and reports the median wall time, CPU time (user plus
system), and peak resident memory. Output is counted, then discarded, so disk speed
doesn't affect the timings.

Workloads:
  presets  Every preset in presets/configs/, PT6H at its own default -w and -i.
           Short runs, so Python start-up is a large share of each time.
  heavy    Sustained P1D runs on the busiest presets, plus a stress run with
           thousands of concurrent sessions (ecommerce at -i 0.05, -w 1,000,000),
           where per-session memory dominates.

Save a baseline before an engine change, then compare after it:

    python tools/bench_engine/bench_engine.py --out /tmp/before.json
    python tools/bench_engine/bench_engine.py --compare /tmp/before.json

Other examples:

    python tools/bench_engine/bench_engine.py --suite heavy --runs 5
    python tools/bench_engine/bench_engine.py --suite heavy --tracemalloc

A markdown table goes to stdout; progress goes to stderr.
"""

import argparse
import glob
import json
import os
import statistics
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
START = "2024-01-01T00:00:00"
SEED = "42"

HEAVY = {
    "vpc_flow_logs P1D": ["-c", "presets/configs/vpc_flow_logs.json", "-r", "P1D"],
    "endpoint_network P1D": [
        "-c",
        "presets/configs/endpoint_network.json",
        "-r",
        "P1D",
    ],
    "ecommerce_sports P1D": [
        "-c",
        "presets/configs/ecommerce_sports.json",
        "-r",
        "P1D",
    ],
    "zscaler_web P1D": ["-c", "presets/configs/zscaler_web.json", "-r", "P1D"],
    "ecommerce stress": [
        "-c",
        "presets/configs/ecommerce.json",
        "-r",
        "PT30M",
        "-i",
        "0.05",
        "-w",
        "1000000",
    ],
}

# Runs generator.py in-process under tracemalloc and reports Python's own peak
# allocation, which isn't affected by allocator fragmentation the way RSS is.
TRACEMALLOC_WRAPPER = """
import os, runpy, sys, tracemalloc
sys.path.insert(0, os.getcwd())
sys.argv = ["generator.py", *sys.argv[1:]]
tracemalloc.start()
try:
    runpy.run_path("generator.py", run_name="__main__")
except SystemExit:
    pass
sys.stderr.write("TRACEMALLOC_PEAK %d\\n" % tracemalloc.get_traced_memory()[1])
"""


def workloads(suite):
    """Return {name: generator.py arguments} for the chosen suite."""
    out = {}
    if suite in ("presets", "all"):
        for cfg in sorted(
            glob.glob(os.path.join(REPO, "presets", "configs", "*.json"))
        ):
            name = os.path.basename(cfg)[:-5]
            out[f"{name} PT6H"] = ["-c", os.path.relpath(cfg, REPO), "-r", "PT6H"]
    if suite in ("heavy", "all"):
        out.update(HEAVY)
    return out


def run_once(args, tracemalloc=False):
    """Run generator.py once and return (wall_s, cpu_s, peak_rss_mb, rows, traced_peak_mb)."""
    full = [*args, "-s", START, "--seed", SEED]
    if tracemalloc:
        cmd = [sys.executable, "-c", TRACEMALLOC_WRAPPER, *full]
    else:
        cmd = [sys.executable, "generator.py", *full]
    started = time.perf_counter()
    proc = subprocess.Popen(
        cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    rows = 0
    for chunk in iter(lambda: proc.stdout.read(1 << 20), b""):
        rows += chunk.count(b"\n")
    stderr = proc.stderr.read().decode(errors="replace")
    _, status, usage = os.wait4(proc.pid, 0)
    wall = time.perf_counter() - started
    if os.waitstatus_to_exitcode(status) != 0:
        raise RuntimeError(f"generator.py failed: {' '.join(full)}\n{stderr[-2000:]}")
    # ru_maxrss is in bytes on macOS and kilobytes on Linux.
    rss_mb = usage.ru_maxrss / (1 << 20 if sys.platform == "darwin" else 1 << 10)
    traced = None
    for line in stderr.splitlines():
        if line.startswith("TRACEMALLOC_PEAK "):
            traced = int(line.split()[1]) / (1 << 20)
    return wall, usage.ru_utime + usage.ru_stime, rss_mb, rows, traced


def measure(name, args, runs, tracemalloc):
    """Return the median measurements for one workload over runs repetitions."""
    samples = []
    for i in range(runs):
        print(f"  {name}: run {i + 1}/{runs}", file=sys.stderr, flush=True)
        samples.append(run_once(args))
    result = {
        "wall_s": statistics.median(s[0] for s in samples),
        "wall_spread_s": max(s[0] for s in samples) - min(s[0] for s in samples),
        "cpu_s": statistics.median(s[1] for s in samples),
        "rss_mb": statistics.median(s[2] for s in samples),
        "rows": samples[0][3],
    }
    result["rows_per_s"] = result["rows"] / result["wall_s"]
    if tracemalloc:
        print(f"  {name}: tracemalloc run", file=sys.stderr, flush=True)
        result["traced_peak_mb"] = run_once(args, tracemalloc=True)[4]
    return result


def pct(new, old):
    return f"{100 * (new - old) / old:+.1f}%" if old else "n/a"


def print_table(results, baseline):
    traced = any("traced_peak_mb" in r for r in results.values())
    if baseline is None:
        head = [
            "Workload",
            "Rows",
            "Wall (s)",
            "Spread (s)",
            "Rows/s",
            "CPU (s)",
            "Peak RSS (MB)",
        ]
        if traced:
            head.append("Traced peak (MB)")
        print("| " + " | ".join(head) + " |")
        print("|" + "|".join(" --- " for _ in head) + "|")
        for name, r in results.items():
            cells = [
                name,
                f"{r['rows']:,}",
                f"{r['wall_s']:.2f}",
                f"±{r['wall_spread_s']:.2f}",
                f"{r['rows_per_s']:,.0f}",
                f"{r['cpu_s']:.2f}",
                f"{r['rss_mb']:.1f}",
            ]
            if traced:
                cells.append(
                    f"{r['traced_peak_mb']:.1f}" if "traced_peak_mb" in r else ""
                )
            print("| " + " | ".join(cells) + " |")
        return
    head = [
        "Workload",
        "Wall (s)",
        "Change",
        "CPU (s)",
        "Change",
        "Peak RSS (MB)",
        "Change",
        "Rows",
    ]
    print("| " + " | ".join(head) + " |")
    print("|" + "|".join(" --- " for _ in head) + "|")
    for name, r in results.items():
        b = baseline.get(name)
        if b is None:
            print(
                f"| {name} | {r['wall_s']:.2f} | new | {r['cpu_s']:.2f} | | {r['rss_mb']:.1f} | | {r['rows']:,} |"
            )
            continue
        rows = "same" if r["rows"] == b["rows"] else f"{b['rows']:,} → {r['rows']:,}"
        print(
            f"| {name} | {b['wall_s']:.2f} → {r['wall_s']:.2f} | {pct(r['wall_s'], b['wall_s'])} "
            f"| {b['cpu_s']:.2f} → {r['cpu_s']:.2f} | {pct(r['cpu_s'], b['cpu_s'])} "
            f"| {b['rss_mb']:.1f} → {r['rss_mb']:.1f} | {pct(r['rss_mb'], b['rss_mb'])} | {rows} |"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--suite",
        choices=["presets", "heavy", "all"],
        default="all",
        help="Which workloads to run (default: all).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Runs per workload; the median is reported (default: 3).",
    )
    parser.add_argument("--out", help="Save results as JSON, for a later --compare.")
    parser.add_argument("--compare", help="Baseline JSON from an earlier --out run.")
    parser.add_argument(
        "--tracemalloc",
        action="store_true",
        help="Also measure Python's traced peak allocation, in one extra "
        "(much slower) run per workload.",
    )
    args = parser.parse_args()

    baseline = None
    if args.compare:
        with open(args.compare) as f:
            baseline = json.load(f)

    results = {}
    for name, wl_args in workloads(args.suite).items():
        results[name] = measure(name, wl_args, args.runs, args.tracemalloc)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)
    print_table(results, baseline)


if __name__ == "__main__":
    main()
