# simpy prototype (spike, not production)

A working prototype of an alternative execution model for the generator engine:
one coroutine per session in a single-threaded `simpy` event loop, instead of
today's one-OS-thread-per-session model in `ieg/core.py`. Branch:
`20260901-simpy-engine`, off `20260828-queues`.

## Run it

```bash
python -m tools.simpy_prototype.generate -c presets/configs/ssh_auth.json -w 100 -i 10 -n 50 -t linux_secure
```

Flags mirror `generator.py`'s own (`-c`, `-w`, `-i`, `-r`/`-n`, `-t`, `--schedule`, `-p`, `--seed`, `-s`).

## Why

`spawning_thread`'s admission gate (semaphore + occupancy-scaled backoff,
`20260828-queues`) exists entirely to solve one problem: efficiently noticing
when a worker slot is free, without polling. `simpy.Resource` solves the same
problem natively — a session either gets a free slot immediately or waits,
woken the instant one releases, with no retry loop and no rejection path.
Adopting it removes the semaphore, the backoff, and the cap formula entirely,
not just makes them faster.

## What's been verified

- **Translation correctness** (Stage 1): byte-identical output vs. the thread
  engine, same seed, across all 11 presets with real templates, 15 seeds
  each — but **single-session only**. Concurrent-session timestamp
  correctness is verified separately (see below), not by this byte-diff.
- **Concurrency ceiling** (Stage 2): `simpy.Resource(capacity=w)` reproduces
  the Little's Law plateau correctly — linear growth in throughput below a
  config's natural ceiling, flat above it — matching `estimate_session_length`'s
  prediction (`ieg/states.py`).
- **Schedule grow/shrink** (Stage 3): grow = bump `pool._capacity` and call
  `pool._trigger_put(None)` to wake anyone queued; shrink = just lower
  `_capacity`. No `held_back` bookkeeping needed — `simpy.Resource._do_put`
  only ever checks capacity for *new* requests, so already-granted sessions
  are never touched. Stress-tested over 2 simulated days of `ecommerce`'s real
  schedule: 145,223 grow/shrink transitions, zero admission violations.
- **Scale past today's ceiling** (Stage 4): `generator.py`'s `MAX_WORKERS` hard
  limit (10,000 as of `20260828-queues`) exists because real OS thread-creation
  failures were observed in that range on the test machine. The coroutine
  model has no such ceiling: cost is flat from `w=2,500` to `w=100,000` when
  the extra capacity isn't needed (governed by real utilization, not the
  capacity number), and for a config whose *natural* ceiling genuinely exceeds
  10,000, throughput keeps climbing past that point instead of being
  artificially capped.
- **Efficiency at real production settings**: measured against
  `20260828-queues` (not `main` — the fully-tuned thread engine, the hardest
  comparison available), at every profile's actual calibrated `tiny`-tier
  settings from `tools/generate_all.json`: 34-67% of the thread engine's CPU
  time and wall-clock, every single profile, no exceptions. At `zscaler_web`'s
  higher-volume `medium` tier (`w=1500`): 36% CPU, 51% memory, 43% wall-clock.

## Known gaps (not yet done)

- **Concurrent-session correctness under real load** was verified narrowly:
  `session_process`/`arrival_process` derive `driver.global_clock.sim_time`
  fresh from `env.now` after every yield (see the docstring in `generate.py`)
  specifically because an earlier, incremental-accumulation version corrupted
  silently under real concurrency (many sessions each advancing the same
  shared clock independently races it far ahead of true elapsed time, which
  then corrupts `Controller.is_done()`'s runtime check too, since it reads the
  same clock). Fixed and spot-checked at `w=8025`, not exhaustively verified
  across presets/scales the way Stage 1-4 were.
- **Distributional equivalence** (planned Stage 6) has not been run: row-count
  and timing distributions vs. the thread engine, across all 11 presets, many
  seeds. Exact output can't match under concurrency (RNG draw order differs
  between a coroutine event loop and OS-thread scheduling, even at the same
  `--seed`) — "equivalent," not "identical," is the right bar, same as any
  admission-timing change (see `feedback_verification_scope` in project
  memory).
- **Real-time mode** (`simpy.rt.RealtimeEnvironment` vs. today's plain
  `time.sleep`), `--partition` under real concurrency, and OCSF/template
  validation via `tools/ocsf/validate.py` haven't been exercised through this
  path yet.
- This is a single-file prototype, not integrated with `generator.py`'s CLI
  or `DataDriver.simulate()`. A real adoption would replace `Clock` and
  `spawning_thread`/`worker_thread` in `ieg/core.py`, not live alongside them
  in `tools/`.
