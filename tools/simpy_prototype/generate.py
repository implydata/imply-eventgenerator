"""A single-process, coroutine-based generation path built on simpy, as an
alternative to core.py's one-OS-thread-per-session model. See README.md in
this directory for status, findings, and what's not yet covered.

Reuses DataDriver's own state-machine walk, distribution sampling, and _emit()
(headers, partition boundaries) unchanged -- only the concurrency/scheduling
layer differs. simpy.Resource(capacity=w) replaces the semaphore+backoff
admission gate entirely: a session either gets a free slot immediately or
waits, woken the instant one frees, with no polling and no rejection path.

Simulated time comes from simpy's own env.now, always read fresh right after
each yield -- never accumulated locally -- because env.now is already
correctly time-ordered across every concurrently-interleaved session by
simpy's own event queue. An earlier version accumulated
driver.global_clock.sim_time incrementally per call site; that only happens to
be safe with a single in-flight session, and silently corrupts under real
concurrency (many sessions each advancing the same shared clock independently
races it far ahead of true elapsed time, which then corrupts runtime-based end
conditions too, since those read the same clock).
"""
import argparse
import json
import random
import sys
from datetime import datetime, timedelta

import isodate
import numpy as np
import simpy

from ieg.core import DataDriver
from ieg.distributions import parse_distribution, parse_schedule


def run(config_path, w, i, start_time, duration_iso=None, total_recs=None,
        template_name=None, schedule_path=None, partition_iso=None, seed=42):
    """Run one simpy-based simulation and return the total record count.

    Output goes to stdout via DataDriver._emit(), same as generator.py.
    """
    random.seed(seed)
    np.random.seed(seed)

    with open(config_path) as f:
        cfg = json.load(f)
    driver = DataDriver("x", cfg, runtime=duration_iso, total_recs=total_recs, time_type="SIM",
                         start_time=start_time, max_entities=w, template_name=template_name,
                         partition_interval=partition_iso)
    driver.rate_delay = parse_distribution({"type": "exponential", "mean": float(i)}, clock=driver.global_clock)

    schedule = None
    if schedule_path:
        with open(schedule_path) as f:
            schedule_desc = json.load(f)
        schedule = parse_schedule(schedule_desc, driver.global_clock)

    env = simpy.Environment()
    pool = simpy.Resource(env, capacity=w)
    effective_max = w

    def update_capacity():
        # capacity is a read-only property wrapping _capacity in simpy's
        # BaseResource -- grow bumps _capacity and wakes anyone queued
        # (_trigger_put); shrink just lowers _capacity, which is enough on its
        # own, since _do_put only ever checks capacity for *new* requests --
        # sessions already granted are never touched, so in-flight work is
        # never interrupted, with no held-back bookkeeping needed.
        nonlocal effective_max
        if schedule is None:
            return
        new_effective_max = max(1, int(w * schedule.get_multiplier()))
        if new_effective_max != effective_max:
            delta = new_effective_max - effective_max
            pool._capacity += delta
            if delta > 0:
                pool._trigger_put(None)
            effective_max = new_effective_max

    def session_process():
        with pool.request() as req:
            yield req
            current_state = driver.initial_state
            variables = {}
            while True:
                delta = float(current_state.delay.get_sample())
                if delta > 0:
                    yield env.timeout(delta)
                    driver.global_clock.sim_time = start_time + timedelta(seconds=env.now)
                driver.set_variable_values(variables, current_state.variables)
                if current_state.dimensions is not None:
                    record = driver.create_record(current_state.dimensions, variables)
                    formatted_record = driver.render_record(record)
                    driver._emit(formatted_record, driver.global_clock.now())
                    driver.sim_control.inc_rec_count()
                if driver.sim_control.is_done():
                    return
                next_state_name = current_state.get_next_state_name()
                if next_state_name is None:
                    break
                next_state = driver.states.get(next_state_name)
                if next_state is None or next_state.type == "event:end":
                    break
                current_state = next_state

    def arrival_process():
        while not driver.sim_control.is_done():
            delta = float(driver.rate_delay.get_sample())
            yield env.timeout(delta)
            driver.global_clock.sim_time = start_time + timedelta(seconds=env.now)
            update_capacity()
            env.process(session_process())

    env.process(arrival_process())
    if duration_iso:
        parsed = isodate.parse_duration(duration_iso)
        end_seconds = (start_time + parsed - start_time).total_seconds() if hasattr(parsed, 'total_seconds') else parsed.total_seconds()
        env.run(until=end_seconds)
    else:
        env.run()
    return driver.sim_control.get_record_count()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", required=True, help="Config file path")
    parser.add_argument("-w", type=int, required=True, help="Concurrent worker (pool) capacity")
    parser.add_argument("-i", type=float, required=True, help="Interarrival mean, seconds")
    parser.add_argument("-r", dest="duration_iso", default=None, help="ISO 8601 duration, e.g. P1D")
    parser.add_argument("-n", dest="total_recs", type=int, default=None)
    parser.add_argument("-t", dest="template_name", default=None)
    parser.add_argument("--schedule", dest="schedule_path", default=None)
    parser.add_argument("-p", dest="partition_iso", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("-s", dest="start_time", default="2024-01-01T00:00:00")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start_time)
    count = run(args.c, args.w, args.i, start, args.duration_iso, args.total_recs,
                args.template_name, args.schedule_path, args.partition_iso, args.seed)
    print(f"total records: {count}", file=sys.stderr)
