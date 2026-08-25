"""Core engine: Clock, DataDriver, and record rendering.

Clock manages simulated and real-time scheduling across worker threads.
DataDriver is the top-level driver: it parses a generator config, builds the
state machine, spawns worker threads, and writes rendered records to stdout.
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta

import isodate
from sortedcontainers import SortedList

from ieg.dimensions import DimensionTimestampClock, DimensionVariable, get_dimensions, get_variables
from ieg.distributions import parse_distribution, parse_schedule
from ieg.states import Controller, State, Transition
from ieg.validate import validate_config

from jinja2 import Environment, Undefined, UndefinedError

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

_EPOCH = datetime(1970, 1, 1)


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

class FutureEvent:
    """A future event in the simulation clock, used to manage simulated time ordering."""

    def __init__(self, t):
        self.t = t
        self.name = threading.current_thread().name
        self.event = threading.Event()
    def get_time(self):
        """Return the scheduled time of this event."""
        return self.t

    def get_name(self):
        """Return the thread name that created this event."""
        return self.name

    def __lt__(self, other):
        return self.t < other.t

    def __eq__(self, other):
        return self.t == other.t

    def __str__(self):
        return 'FutureEvent('+self.name+', '+str(self.t)+')'

    def pause(self):
        """Block the current thread until this event is resumed."""
        logger.debug("%s pausing", self.name)
        self.event.clear()
        self.event.wait()

    def resume(self):
        """Unblock the thread waiting on this event."""
        logger.debug("%s resuming", self.name)
        self.event.set()

class Clock:
    """Manages time for all worker threads, supporting real-time and simulated modes.

    In simulated mode (time_type != 'REAL'), threads coordinate via a shared sorted
    event queue: each sleeping thread registers a FutureEvent, and only the thread
    with the earliest scheduled time is allowed to run. This produces deterministic,
    serialised output when combined with --seed.

    In real-time mode, sleep() delegates to time.sleep() with no coordination.
    """

    future_events = SortedList()
    active_threads = 0
    lock = threading.Lock()
    sleep_lock = threading.Lock()

    def __init__(self, time_type, start_time = datetime.now()):
        self.sim_time = start_time
        self.start_time = start_time
        self.time_type = time_type

    def __str__(self):
        s = 'Clock(time='+str(self.sim_time)
        for e in self.future_events:
            s += ', '+str(e)
        s += ')'
        return s

    def get_duration(self):
        """Return elapsed seconds since the clock started."""
        time_delta = self.now() - self.start_time
        return time_delta.total_seconds()

    def get_start_time(self):
        """Return the start time of this clock."""
        return self.start_time

    def activate_thread(self):
        """Register a thread as active for simulated time coordination."""
        if self.time_type != 'REAL':
            self.lock.acquire()
            self.active_threads += 1
            self.lock.release()

    def deactivate_thread(self):
        """Unregister a thread from simulated time coordination."""
        if self.time_type != 'REAL':
            self.lock.acquire()
            self.active_threads -= 1
            self.lock.release()

    def end_thread(self):
        """Unregister a thread and resume the next pending event if any."""
        if self.time_type != 'REAL':
            self.lock.acquire()
            self.active_threads -= 1
            if len(self.future_events) > 0:
                self.remove_event().resume()
            self.lock.release()

    def release_all(self):
        """Resume all pending future events."""
        if self.time_type != 'REAL':
            self.lock.acquire()
            logger.debug("release_all - active_threads = %d", self.active_threads)
            for e in self.future_events:
                e.resume()
            self.lock.release()

    def add_event(self, future_t):
        """Schedule a new future event at the given time and return it."""
        this_event = FutureEvent(future_t)
        self.future_events.add(this_event)
        logger.debug("add_event (after) %s - %s", threading.current_thread().name, self)
        return this_event

    def remove_event(self):
        """Remove and return the earliest future event."""
        logger.debug("remove_event (before) %s - %s", threading.current_thread().name, self)
        next_event = self.future_events[0]
        self.future_events.remove(next_event)
        return next_event

    def pause(self, event):
        """Pause the current thread on the given event, releasing the lock while waiting."""
        self.active_threads -= 1
        self.lock.release()
        event.pause()
        self.lock.acquire()
        self.active_threads += 1

    def resume(self, event):
        """Resume a paused event."""
        event.resume()

    def now(self) -> datetime:
        """Return the current time (simulated or real depending on mode)."""
        if self.time_type != 'REAL':
            t = self.sim_time
        else:
            t = datetime.now()
        return t

    def sleep(self, delta):
        """Sleep for delta seconds. In simulated mode, advances sim time instead of waiting."""
        if delta <= 0:
            return
        if self.time_type != 'REAL': # Simulated time
            self.lock.acquire()
            logger.debug("%s begin sleep %s + %s", threading.current_thread().name, self.sim_time, delta)
            this_event = self.add_event(self.sim_time + timedelta(seconds=delta))
            logger.debug("%s active threads %d", threading.current_thread().name, self.active_threads)
            if self.active_threads == 1:
                next_event = self.remove_event()
                if str(this_event) != str(next_event):
                    self.resume(next_event)
                    logger.debug("%s start pause if", threading.current_thread().name)
                    self.pause(this_event)
                    logger.debug("%s end pause if", threading.current_thread().name)
            else:
                logger.debug("%s start pause else", threading.current_thread().name)
                self.pause(this_event)
                logger.debug("%s end pause else", threading.current_thread().name)
            self.sim_time = this_event.get_time()
            self.lock.release()
            # if new time is past current time and the simulation is SIM_REAL, switch to REAL and continue in real-time
            if self.time_type == 'SIM_TO_REAL' and self.sim_time > datetime.now():
                self.time_type = 'REAL'
                self.sim_time = datetime.now()
        else: # Real time
            time.sleep(delta)

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
        self.fatal_error = None

        if partition_interval is None:
            self.partition_interval = None
        else:
            try:
                parsed_partition_interval = isodate.parse_duration(partition_interval).total_seconds()
            except Exception as e:
                raise ValueError(f"Error parsing --partition duration '{partition_interval}': {e}")
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

    def worker_thread(self):
        """Process the state machine, generating records and sending them to the output target."""
        self.global_clock.activate_thread()
        current_state = self.initial_state
        variables = {}
        while True:
            if current_state is None:
                raise RuntimeError("Unexpected error: current state of the state machine is None.")
            if current_state.type == 'event:start:timer':
                logger.debug("Thread %s starting process instance", threading.current_thread().name)
            # Process delay
            delta = float(current_state.delay.get_sample())
            self.global_clock.sleep(delta)
            self.status_msg=f"Running, Sim Clock: {self.global_clock.now()}"
            # Set variables (activities only; evaluated before emission)
            self.set_variable_values(variables, current_state.variables)
            # Only emit record if state has dimensions (emitter was specified)
            if current_state.dimensions is not None:
                record = self.create_record(current_state.dimensions, variables)
                formatted_record = self.render_record(record)
                self._emit(formatted_record, self.global_clock.now())
                self.sim_control.inc_rec_count()
            if self.sim_control.is_done():
                break
            next_state_name = current_state.get_next_state_name()
            if next_state_name is None:
                break
            next_state = self.states.get(next_state_name)
            if next_state is None or next_state.type == 'event:end':
                logger.debug("Thread %s reached event:end", threading.current_thread().name)
                break
            current_state = next_state

        self.global_clock.end_thread()
        self.sim_control.remove_entity()

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

    def spawning_thread(self):
        """Spawn worker threads at the rate set by the event:start:timer's cardinality_distribution."""
        self.global_clock.activate_thread()

        # Spawn the workers in a separate thread so we can stop the whole thing in the middle of spawning if necessary
        while not self.sim_control.is_done():
            multiplier = self.schedule.get_multiplier() if self.schedule else 1.0
            effective_max = max(1, int(self.max_entities * multiplier))
            if self.sim_control.get_entity_count() < effective_max:
                thread_name = 'W'+str(self.sim_control.get_entity_count())
                self.sim_control.add_entity()
                t = threading.Thread(target=self.worker_thread, name=thread_name, daemon=True)
                try:
                    t.start()
                except RuntimeError as e:
                    # Hit an OS thread-creation limit (e.g. macOS kern.num_taskthreads,
                    # Linux RLIMIT_NPROC) — an operating-system ceiling, not a data-volume
                    # one. spawning_thread runs off the main thread, so this must be handed
                    # back via self.fatal_error rather than raised here, or it would just
                    # print a traceback and the run would silently report success.
                    self.sim_control.remove_entity()
                    self.fatal_error = RuntimeError(
                        f"Hit the operating system's thread-creation limit at "
                        f"{self.sim_control.get_entity_count()} active workers (-w {self.max_entities}). "
                        f"Lower -w and retry — this is an OS limit, not a data-volume limit. ({e})"
                    )
                    self.global_clock.end_thread()
                    return
                # add a sleep event before spawning the next
                self.global_clock.sleep(float(self.rate_delay.get_sample()))
            else:
                self.global_clock.sleep(5.0)

        # shut off clock simulator
        self.global_clock.end_thread()

    def get_new_time_for_record(self):
        """Return the current clock time formatted as a string."""
        return self.global_clock.now().strftime('%Y-%m-%d %H:%M:%S.%f')

    def simulate(self):
        """Start the simulation, spawning workers and running until completion."""
        self.status_msg = f'Starting {self.type} job.'
        thread_name = 'Spawning'
        thrd = threading.Thread(target=self.spawning_thread, args=(), name=thread_name, daemon=True)
        thrd.start()
        thrd.join()
        # spawning_thread runs off the main thread — an exception raised there would
        # otherwise just print a traceback and let this method return normally, making
        # a crashed run look like it completed. Re-raise here so it actually fails.
        if self.fatal_error is not None:
            raise self.fatal_error

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
