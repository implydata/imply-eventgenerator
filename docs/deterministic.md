# Deterministic generation

Use the `--seed` argument to produce repeatable, deterministic output. When the same seed is used with the same configuration and duration, the generator produces identical data — only the timestamps will differ if a different start time (`-s`) is used.

This is useful for generating consistent sample datasets, reproducible test fixtures, and benchmarking.

## How it works

The `--seed` argument accepts an integer that seeds both random number generators used by the generator (Python's `random` module and NumPy's `np.random`).

Without `--seed`, the generator uses unseeded random state and produces different output on each run.

When combined with simulated time (`-s`), the engine's single-threaded `simpy` event loop processes every scheduled event in a fully deterministic order — there's no OS thread scheduler involved at all. Combined with a fixed seed, this guarantees the same RNG call sequence on every run, producing identical output. `--seed` _can_ be used without `-s` (real-time mode), but deterministic output is only guaranteed in simulated time mode: real-time mode paces the same event loop against actual wall-clock timing, which introduces its own run-to-run jitter.

## Usage

```bash
python generator.py \
  -c <generator configuration file> \
  -s <start timestamp> \
  -r <duration> \
  --seed <integer>
```

| Argument | Description |
| --- | --- |
| `--seed` | An integer seed value. Any integer is valid. The same seed always produces the same data. |
| `-s` | Required for deterministic output. Sets simulated time mode, which processes every event through simpy's own deterministic event queue instead of pacing against real wall-clock time. |

## Example

Generate one day of VPC Flow Logs deterministically:

```bash
python generator.py \
  -c presets/configs/vpc_flow_logs.json \
  -s 2026-02-12T00:00:00 \
  -r P1D \
  --seed 42
```

Running this command again with the same arguments produces identical output. Changing the start time (`-s`) but keeping the same seed produces the same data with different timestamps.
