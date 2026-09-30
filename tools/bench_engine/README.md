# Engine benchmark

`bench_engine.py` measures how fast the engine runs and how much memory it uses,
so you can check that an engine change doesn't make generation slower or
hungrier. It runs `generator.py` several times per workload, with a fixed seed
and the simulated clock, and reports the median wall time, CPU time, and peak
resident memory. Output is counted, then discarded.

## Usage

Save a baseline on the commit before your change, then compare after it:

```bash
git switch main
python tools/bench_engine/bench_engine.py --out /tmp/before.json
git switch my-branch
python tools/bench_engine/bench_engine.py --compare /tmp/before.json
```

| Flag            | Meaning                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------ |
| `--suite`       | `presets`, `heavy`, or `all` (default).                                                          |
| `--runs`        | Runs per workload; the median is reported. Default `3`.                                          |
| `--out`         | Save the results as JSON.                                                                        |
| `--compare`     | Compare against a JSON file saved with `--out`.                                                  |
| `--tracemalloc` | Also measure Python's own peak allocation, in one extra, much slower, run per workload.         |

## Workloads

- **`presets`**: every preset in `presets/configs/`, PT6H at its default `-w`
  and `-i`. These runs take a few seconds each, so Python start-up is a large
  share of each time; expect differences of a few percent between runs.
- **`heavy`**: P1D runs of `vpc_flow_logs`, `endpoint_network`,
  `ecommerce_sports`, and `zscaler_web`, which measure sustained throughput. It
  also includes a stress run, `ecommerce` at `-i 0.05` with `-w 1000000`, which
  keeps thousands of sessions active at once, so per-session memory dominates
  its peak.

## Reading the results

- **Rows** should be `same` in a comparison. A different row count means the
  change altered the generated data, not just its speed. Check that with a
  seeded byte-diff before trusting the timing.
- **Peak RSS** of about 44 MB is the Python interpreter and libraries. Only the
  stress run uses enough memory for an engine change to show.
- **Traced peak** counts only memory that Python allocated, so it's unaffected
  by allocator fragmentation. Use it to confirm a change in peak RSS.
