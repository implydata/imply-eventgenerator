# Deterministic generation

Use the `--seed` argument to produce repeatable, deterministic output. When the same seed is used with the same configuration and duration, the generator produces identical data — only the timestamps will differ if a different start time (`-s`) is used.

This is useful for generating consistent sample datasets, reproducible test fixtures, and benchmarking.

## How it works

The `--seed` argument accepts an integer that seeds both random number generators used by the generator (Python's `random` module and NumPy's `np.random`).

When combined with simulated time (`-s`), thread execution is deterministically serialized via the Clock's sorted event queue. This guarantees the same thread interleaving and the same RNG call sequence on every run, producing identical output.

## Usage

```bash
python generator.py \
  -c <generator specification file> \
  -s <start timestamp> \
  -r <duration> \
  --seed <integer>
```

| Argument | Description |
| --- | --- |
| `--seed` | An integer seed value. Any integer is valid. The same seed always produces the same data. |
| `-s` | Required for deterministic output. Sets simulated time mode, which ensures deterministic thread scheduling. |

## Example

Generate one day of VPC Flow Logs deterministically:

```bash
python generator.py \
  -c conf/gen/vpc_flow_logs.json \
  -f conf/form/vpc_flow_logs.txt \
  -s 2026-02-12T00:00:00 \
  -r P1D \
  --seed 42
```

Running this command again with the same arguments produces identical output. Changing the start time (`-s`) but keeping the same seed produces the same data with different timestamps.

## Notes

- Without `--seed`, the generator uses unseeded random state and produces different output on each run.
- `--seed` can be used without `-s` (real-time mode), but deterministic output is only guaranteed in simulated time mode because real-time thread scheduling is non-deterministic.
