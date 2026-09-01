"""Core engine: Clock, DataDriver, and record rendering.

Clock manages simulated and real-time scheduling for a single-threaded simpy
event loop. DataDriver is the top-level driver: it parses a generator config,
builds the state machine, runs one simpy process per session, and writes
rendered records to stdout.
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta

import isodate
import simpy
import simpy.rt
from jinja2 import Environment, Undefined, UndefinedError

from ieg.dimensions import (
    DimensionTimestampClock,
    DimensionVariable,
    get_dimensions,
    get_variables,
)
from ieg.distributions import parse_distribution, parse_schedule
from ieg.states import Controller, State, Transition
from ieg.validate import validate_config

logger = logging.getLogger('ieg')


class _StrictEnv:
    """Wraps os.environ for Jinja2 templates. Raises UndefinedError on missing
    vars so templates fail loudly, but allows explicit defaults via .get()."""

    def __getattr__(self, name):
        try:
            return os.environ[name]
        except KeyError:
            raise UndefinedError(f"Environment variable '{name}' is not set")

    def __getitem__(self, name):
        return self.__getattr__(name)

    def get(self, name, default=None):
        return os.environ.get(name, default)


_jinja_env = Environment(undefined=Undefined)
_jinja_env.globals['env'] = _StrictEnv()

# Prefixes a --partition marker line. \x1e (ASCII Record Separator) rather than a
# printable string, since no template in this repo renders a line starting with a control
# character — see tools/split_stream.sh, which splits stdout on this exact prefix.
PARTITION_MARKER_PREFIX = '\x1ePARTITION '

# Naive on purpose (noqa: DTZ001) — every datetime this engine works with, real or
# simulated, is naive throughout (see Clock), so _EPOCH must stay naive too or
# `t - _EPOCH` in _partition_bucket below raises on the timezone mismatch.
_EPOCH = datetime(1970, 1, 1)  # noqa: DTZ001


def _partition_bucket(t, interval_seconds):
    """Return the index of the interval_seconds-sized bucket containing t — an
    integer comparison key, checked on every record, so it's cheap: no datetime
    construction, unlike _bucket_start below. Multiplying back by interval_seconds
    and adding it to the epoch (_bucket_start) recovers the boundary datetime, only
    needed the rare time a comparison actually finds a new partition has started.
    """
    return int((t - _EPOCH).total_seconds() // interval_seconds)


def _bucket_start(bucket, interval_seconds):
    """Return the start of partition bucket `bucket` as a calendar-aligned datetime
    (TIME_TRUNC semantics: multiples of interval_seconds since the epoch, so PT1H
    lands on the hour and P1D at midnight) — not an offset from a run's start time.
    """
    return _EPOCH + timedelta(seconds=bucket * interval_seconds)

class Clock:
    """Manages simulated or real time for the engine's simpy-based event loop.

    Backed by a simpy.Environment (virtual time, SIM mode) or
    simpy.rt.RealtimeEnvironment (paced to actual wall-clock time, REAL mode).
    Turn-ordering across concurrently-scheduled sessions is handled entirely by
    simpy's own event queue — every session is a coroutine in one single-
    threaded event loop, not an OS thread, so there is no separate
    thread-coordination protocol to hand-roll here the way there used to be.

    SIM_TO_REAL (switching from simulated to real-time pacing partway through
    a run) is not supported by this implementation: simpy.Environment and
    simpy.rt.RealtimeEnvironment are different pacing engines and a running
    Environment can't be handed over to one mid-run. A config that actually
    needs this has no equivalent here yet — flag it rather than assume it's
    unused, since nothing in this repo's own CLI path sets it, but that
    doesn't rule out an external caller.
    """

    def __init__(self, time_type, start_time=None):
        self.time_type = time_type
        self.start_time = start_time if start_time is not None else datetime.now()
        if time_type == 'REAL':
            # factor=1: one real second per simulated second. strict=False: a
            # step that runs behind schedule logs instead of raising -- this
            # engine has no hard real-time deadline to enforce.
            self.env = simpy.rt.RealtimeEnvironment(factor=1.0, strict=False)
        else:
            self.env = simpy.Environment()

    def __str__(self):
        return f'Clock(time={self.now()})'

    def get_duration(self):
        """Return elapsed seconds since the clock started."""
        return self.env.now

    def get_start_time(self):
        """Return the start time of this clock."""
        return self.start_time

    def now(self) -> datetime:
        """Return the current time (simulated or real depending on mode)."""
        return self.start_time + timedelta(seconds=self.env.now)

    def sleep(self, delta):
        """Generator: `yield from clock.sleep(delta)` advances time by delta seconds.

        Must be driven from within a simpy process (a generator running under
        this Clock's own env) — see DataDriver.session_process/arrival_process.
        """
        if delta <= 0:
            return
        yield self.env.timeout(delta)


class DataDriver:
    """Main driver class for generating data. Handles configuration, state machine, and output targets."""

    def __init__(self, name, config, runtime, total_recs, time_type, start_time, max_entities, schedule_config=None, template_name=None, partition_interval=None):
        self.name = name
        self.config = config

        if not validate_config(config, template_name=template_name):
            raise ValueError("Configuration is invalid — see log output for details.")

        self.runtime = runtime
        self.total_recs = total_recs
        self.time_type = time_type
        self.start_time = start_time
        self.max_entities = max_entities
        self.status_msg = 'Creating...'
        self.header = None
        self.jinja_template = None

        if partition_interval is None:
            self.partition_interval = None
        else:
            try:
                parsed_partition_interval = isodate.parse_duration(partition_interval)
            except Exception as e:
                raise ValueError(f"Error parsing --partition duration '{partition_interval}': {e}")
            if isinstance(parsed_partition_interval, isodate.Duration):
                # Unlike -r (a one-time span, resolved against the actual start time),
                # --partition is a repeating bucket size used as a fixed number of
                # seconds (_partition_bucket). A calendar month resolved once would
                # only be correct for the first bucket — every later one would drift
                # out of true calendar alignment (Feb is shorter than Jan, etc.).
                raise ValueError(
                    f"--partition duration '{partition_interval}' uses a calendar-based "
                    f"unit (Y or M), which isn't a fixed size — use P1D, PT1H, P7D, etc."
                )
            parsed_partition_interval = parsed_partition_interval.total_seconds()
            if parsed_partition_interval <= 0:
                raise ValueError(f"--partition duration '{partition_interval}' must be positive.")
            self.partition_interval = parsed_partition_interval

        if template_name is not None:
            templates = config.get('templates', {})
            if template_name not in templates:
                available = ', '.join(templates.keys()) if templates else 'none'
                raise ValueError(f"Template '{template_name}' not found in config. Available: {available}")
            tmpl = templates[template_name]
            self.jinja_template = _jinja_env.from_string(tmpl['body'])
            if self.header is None and 'header' in tmpl:
                self.header = tmpl['header']

        #
        # Set up the global clock
        #

        self.global_clock = Clock(time_type, start_time)
        self.sim_control = Controller(total_recs, runtime, self.global_clock)
        self.schedule = parse_schedule(schedule_config, self.global_clock) if schedule_config else None

        # Always write to stdout
        self._stdout_lock = threading.Lock()
        self.current_partition_bucket = None  # int bucket index once --partition is set
        self.header_printed = False  # only tracked when --partition is not set

        # Remove type validation and default to generator
        self.type = 'generator'

        # Set up emitters list
        self.emitters = {}
        for emitter in self.config['emitters']:
            name = emitter['name']
            dimensions = get_dimensions(emitter['dimensions'], self.global_clock)
            self.emitters[name] = dimensions

        # Set up the state machine
        state_desc = self.config.get('states')
        if not state_desc or not isinstance(state_desc, list) or len(state_desc) == 0:
            raise RuntimeError("The generator configuration has no states defined.")
        self.initial_state = None
        self.states = {}
        for state in state_desc:
            name = state['name']
            state_type = state.get('type')
            if state_type is None:
                raise RuntimeError(f"State '{state.get('name', '?')}' is missing required field 'type'.")
            # Make emitter optional - handle both missing field and explicit null
            emitter_name = state.get('emitter')  # Returns None if not present
            if emitter_name is not None:
                dimensions = self.emitters[emitter_name]
            else:
                dimensions = None  # No emitter = no record emission
            if 'variables' not in state.keys():
                variables = []
            else:
                variables = get_variables(state['variables'], self.global_clock)
            _zero = {'type': 'constant', 'value': 0}
            if state_type == 'event:end':
                delay = parse_distribution(_zero, clock=self.global_clock)
                transitions = []
            elif state_type == 'event:start:timer':
                delay = parse_distribution(_zero, clock=self.global_clock)
                transitions = [Transition(state['next'], 1.0)]
            elif state_type == 'event:intermediate:timer':
                delay = parse_distribution(state['cardinality_distribution'], clock=self.global_clock)
                transitions = [Transition(state['next'], 1.0)]
            elif state_type == 'activity':
                delay = parse_distribution(_zero, clock=self.global_clock)
                transitions = [Transition(state['next'], 1.0)]
            elif state_type == 'gateway:exclusive':
                delay = parse_distribution(_zero, clock=self.global_clock)
                transitions = Transition.parse_transitions(state['transitions'])
            else:
                delay = parse_distribution(_zero, clock=self.global_clock)
                transitions = Transition.parse_transitions(state.get('transitions', []))
            this_state = State(name, state_type, dimensions, delay, transitions, variables)
            self.states[name] = this_state
            if state_type == 'event:start:timer':
                self.initial_state = this_state

        if self.initial_state is None:
            raise RuntimeError("Config has no event:start:timer state.")

        # Interarrival rate comes from the event:start:timer state's cardinality_distribution field
        timer_desc = next(s for s in state_desc if s.get('type') == 'event:start:timer')
        self.rate_delay = parse_distribution(timer_desc['cardinality_distribution'], clock=self.global_clock)

        # Admission gate for -w: a session either gets a free pool slot
        # immediately or waits, woken the instant one releases -- no polling,
        # no retry loop, no rejection path to back off from. effective_max is
        # tracked separately from pool.capacity (a read-only property; see
        # _update_effective_max) purely so schedule changes only need to
        # compute a delta against the last-known value.
        if self.schedule:
            self._effective_max = max(1, int(self.max_entities * self.schedule.get_multiplier()))
        else:
            self._effective_max = self.max_entities
        self._pool = simpy.Resource(self.global_clock.env, capacity=self._effective_max)

        # Every currently-running arrival_process/session_process, so _end_run
        # can force them all to wake immediately once is_done() becomes true —
        # in SIM mode this is a no-op (waking early vs. naturally makes no
        # real-world time difference), but in REAL mode a session/the arrival
        # loop can otherwise sit waiting on an already-scheduled future delay
        # for real wall-clock seconds after the last record has already been
        # written, well past when the run should actually end.
        self._active_procs = []
        self._ending = False


    def render_record(self, record):
        """Render a record as a Jinja2 template string, or plain JSON if no template is active."""
        if self.jinja_template is not None:
            return self.jinja_template.render(**record)
        for key, value in record.items():
            if isinstance(value, datetime):
                record[key] = value.isoformat()
        return json.dumps(record)

    def create_record(self, dimensions, variables):
        """Build a record dict from dimensions and variable values."""
        record = {}
        for element in dimensions:
            if isinstance(element, DimensionVariable):
                record[element.name] = variables[element.variable_name]
            else:
                if isinstance(element, DimensionTimestampClock) or not element.is_missing():
                    record[element.name] = element.get_stochastic_value()
        return record

    def set_variable_values(self, variables, dimensions):
        """Sample stochastic values from dimensions and store them in the variables dict."""
        for d in dimensions:
            variables[d.name] = d.get_stochastic_value()

    def _end_run(self):
        """Force every currently-running process to wake immediately, once
        (guarded by self._ending), instead of waiting out its own natural
        future delay -- see the comment on self._active_procs in __init__ for
        why. Safe to call from any process, including one of the ones being
        interrupted: a process can't interrupt itself, so it's skipped, but it
        already knows to stop (it just called this from its own is_done()
        check) and will exit on its own.
        """
        if self._ending:
            return
        self._ending = True
        logger.debug("_end_run: interrupting %d active procs at sim time %s",
                     len(self._active_procs), self.global_clock.now())
        for proc in list(self._active_procs):
            if proc.is_alive:
                try:
                    proc.interrupt()
                    logger.debug("_end_run: interrupted %s", proc)
                except RuntimeError:
                    logger.debug("_end_run: could not interrupt %s (self or already terminated)", proc)

    def session_process(self):
        """A simpy process: wait for a free pool slot, then walk the state
        machine, generating records and sending them to the output target.

        Manages the pool request explicitly rather than via `with
        pool.request() as req:` — a request interrupted before it's granted
        must be cancel()'d, not release()'d: releasing a request simpy never
        actually granted still triggers a fresh _trigger_put() scan as a side
        effect, which can admit a *different*, still-queued session that
        _end_run's interrupt sweep already passed over — an uninterrupted,
        untracked session left running after the run was supposed to end.
        """
        proc = self.global_clock.env.active_process
        self._active_procs.append(proc)
        logger.debug("session_process %s: requesting a pool slot at sim time %s", proc, self.global_clock.now())
        req = self._pool.request()
        try:
            try:
                yield req
            except simpy.Interrupt:
                logger.debug("session_process %s: interrupted while queued, cancelling request", proc)
                req.cancel()
                return
            self.sim_control.add_entity()
            logger.debug("session_process %s: admitted at sim time %s", proc, self.global_clock.now())
            try:
                # This session may have been queued for a while; the
                # record-count or runtime end condition could have been
                # reached before its turn came. Check before doing any real
                # work, not just at each step below, so a backlog of queued
                # sessions drains quickly instead of each one doing a full
                # run for nothing.
                if self.sim_control.is_done():
                    logger.debug("session_process %s: is_done() already true on admission, exiting without running", proc)
                    self._end_run()
                    return
                current_state = self.initial_state
                variables = {}
                while True:
                    if current_state is None:
                        raise RuntimeError("Unexpected error: current state of the state machine is None.")
                    # Process delay
                    delta = float(current_state.delay.get_sample())
                    try:
                        yield from self.global_clock.sleep(delta)
                    except simpy.Interrupt:
                        logger.debug("session_process %s: interrupted mid-delay at state %s, exiting", proc, current_state.name)
                        break
                    self.status_msg = f"Running, Sim Clock: {self.global_clock.now()}"
                    # Set variables (activities only; evaluated before emission)
                    self.set_variable_values(variables, current_state.variables)
                    # Only emit record if state has dimensions (emitter was specified)
                    if current_state.dimensions is not None:
                        record = self.create_record(current_state.dimensions, variables)
                        formatted_record = self.render_record(record)
                        self._emit(formatted_record, self.global_clock.now())
                        self.sim_control.inc_rec_count()
                    if self.sim_control.is_done():
                        logger.debug("session_process %s: is_done() became true after emitting, ending run", proc)
                        self._end_run()
                        break
                    next_state_name = current_state.get_next_state_name()
                    if next_state_name is None:
                        break
                    next_state = self.states.get(next_state_name)
                    if next_state is None or next_state.type == 'event:end':
                        break
                    current_state = next_state
            finally:
                self.sim_control.remove_entity()
                self._pool.release(req)
                logger.debug("session_process %s: released its pool slot", proc)
        finally:
            self._active_procs.remove(proc)
            logger.debug("session_process %s: exited, %d active procs remain", proc, len(self._active_procs))

    def _emit(self, formatted_record, record_time):
        """Print formatted_record. Before the first record ever printed — and, once
        --partition is set, again at every later partition boundary — also print the
        header (if the template has one) and a partition marker, all as one atomic
        write, so a downstream csplit-based split always gets self-contained files.

        A stray out-of-order record (see the Clock's zero-delay race window) that
        truncates to an earlier bucket than the one already open is just appended to
        the current partition rather than reopening a past one — markers must stay
        monotonically increasing for the split to make sense.
        """
        with self._stdout_lock:
            lines = []
            if self.partition_interval is not None:
                bucket = _partition_bucket(record_time, self.partition_interval)
                is_first = self.current_partition_bucket is None
                if is_first or bucket > self.current_partition_bucket:
                    self.current_partition_bucket = bucket
                    # The very first partition may be shorter than one interval if -s
                    # doesn't itself fall on a boundary — label it with the true start
                    # time, not the truncated boundary before it, which data never covers.
                    marker_time = self.start_time if is_first else _bucket_start(bucket, self.partition_interval)
                    lines.append(f'{PARTITION_MARKER_PREFIX}{marker_time.isoformat()}')
                    # A run piped through tools/split_stream.sh writes nothing to its
                    # destination until the whole thing finishes (ieg/core.py doesn't
                    # know or care that it's piped) — this is the only sign of life
                    # visible on stderr in the meantime, at the one cadence the engine
                    # already has a natural reason to pause at.
                    logger.info("Partition boundary: %s (%d records so far)",
                                marker_time.isoformat(), self.sim_control.get_record_count())
                    if self.header:
                        lines.append(self.header)
            elif not self.header_printed:
                self.header_printed = True
                if self.header:
                    lines.append(self.header)
            lines.append(formatted_record)
            for line in lines:
                sys.stdout.write(str(line) + '\n')
            sys.stdout.flush()

    def _update_effective_max(self):
        """Grow or shrink the pool to match the schedule's current multiplier.

        capacity is a read-only property wrapping simpy.Resource's own
        _capacity, so growing means bumping _capacity and calling
        _trigger_put(None) to wake anyone already queued now that there's
        room; shrinking just lowers _capacity. That's the whole mechanism --
        no held-back bookkeeping needed, because simpy.Resource only ever
        checks capacity for *new* requests (_do_put); a session already
        granted a slot is never touched, so shrinking can never interrupt
        in-flight work.
        """
        if not self.schedule:
            return
        effective_max = max(1, int(self.max_entities * self.schedule.get_multiplier()))
        if effective_max != self._effective_max:
            delta = effective_max - self._effective_max
            self._pool._capacity += delta
            if delta > 0:
                self._pool._trigger_put(None)
            self._effective_max = effective_max

    def arrival_process(self):
        """A simpy process: start one new session_process at the rate set by
        the event:start:timer's cardinality_distribution.

        Arrivals are unconditional -- there's no admission check here at all,
        and so no rejection path to retry or back off from. Each spawned
        session_process waits for its own pool slot if one isn't immediately
        free, woken the instant one releases.
        """
        proc = self.global_clock.env.active_process
        self._active_procs.append(proc)
        try:
            while not self.sim_control.is_done():
                delta = float(self.rate_delay.get_sample())
                try:
                    yield from self.global_clock.sleep(delta)
                except simpy.Interrupt:
                    logger.debug("arrival_process: interrupted at sim time %s", self.global_clock.now())
                    break
                self._update_effective_max()
                new_proc = self.global_clock.env.process(self.session_process())
                logger.debug("arrival_process: spawned %s at sim time %s", new_proc, self.global_clock.now())
            self._end_run()
        finally:
            self._active_procs.remove(proc)

    def get_new_time_for_record(self):
        """Return the current clock time formatted as a string."""
        return self.global_clock.now().strftime('%Y-%m-%d %H:%M:%S.%f')

    def simulate(self):
        """Start the simulation, running until completion.

        Steps the env manually rather than calling env.run() (which runs
        until its event queue is empty): interrupting a process (_end_run)
        detaches it from whatever event it was waiting on, but doesn't
        remove that event from the queue -- it stays there, scheduled for
        its original time, and simpy runs it anyway once nothing is left
        that's earlier (a harmless no-op, since the interrupted process's
        callback was already detached). In SIM mode that costs nothing --
        processing a no-op event doesn't advance real time. In REAL mode it
        costs exactly what it would have without the interrupt: step() still
        sleeps in real wall-clock time until that event's original moment,
        for every such leftover event, one at a time. Checking the real stop
        condition (is_done() and no active procs left) before each step(),
        rather than relying on the queue draining naturally, means the loop
        exits the instant nothing meaningful remains, instead of after
        waiting out however many orphaned events happen to still be queued.
        """
        self.status_msg = f'Starting {self.type} job.'
        env = self.global_clock.env
        env.process(self.arrival_process())
        while self._active_procs or not self.sim_control.is_done():
            try:
                env.step()
            except simpy.core.EmptySchedule:
                break

    def terminate(self):
        """Terminate the simulation."""
        self.sim_control.terminate()

    def report(self):
        """Return a dict of simulation status and statistics."""
        return {  'name': self.name,
                  'config_file': self.config['config_file'],
                  'active_sessions': self.sim_control.get_entity_count(),
                  'total_records': self.sim_control.get_record_count(),
                  'start_time': self.sim_control.get_start_time().strftime('%Y-%m-%d %H:%M:%S'),
                  'run_time': self.sim_control.get_duration(),
                  'status' : 'COMPLETE' if self.sim_control.is_done() else 'RUNNING',
                  'status_msg' : self.status_msg
                }
