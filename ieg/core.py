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


from sortedcontainers import SortedList

from ieg.dimensions import DimensionGeneratorClock, DimensionVariable, get_dimensions, get_variables
from ieg.distributions import parse_distribution, parse_schedule
from ieg.states import (Controller,
                        ActivityState, EventEndState, EventStartTimerState,
                        EventStartMessageState, EventIntermediateTimerState,
                        GatewayExclusiveState, SubprocessMultiVariablesState)
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

class FutureEvent:
    """A future event in the simulation clock, used to manage simulated time ordering."""

    def __init__(self, t):
        self.t = t
        self.name = threading.current_thread().name
        self.event = threading.Event()
    def get_time(self):
        return self.t

    def get_name(self):
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
        time_delta = self.now() - self.start_time
        return time_delta.total_seconds()

    def get_start_time(self):
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

    def __init__(self, name, config, runtime, total_recs, time_type, start_time, max_entities, schedule_config=None, template_name=None):
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
        stdout_lock = threading.Lock()
        class _StdoutPrinter:
            def print(self, record):
                with stdout_lock:
                    sys.stdout.write(str(record) + '\n')
                    sys.stdout.flush()
        self.target_printer = _StdoutPrinter()

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
        self.states, self.initial_state = self._parse_states(state_desc)
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
                if isinstance(element, DimensionGeneratorClock) or not element.is_missing():
                    record[element.name] = element.get_stochastic_value()
        return record

    def _parse_event_end(self, state):
        return EventEndState(state['name'])

    def _parse_event_start_timer(self, state):
        return EventStartTimerState(state['name'], state['next'])

    def _parse_gateway_exclusive(self, state):
        transitions = state['transitions']
        return GatewayExclusiveState(
            state['name'],
            [t['next'] for t in transitions],
            [float(t['probability']) for t in transitions]
        )

    def _parse_event_intermediate_timer(self, state):
        delay = parse_distribution(state['cardinality_distribution'], clock=self.global_clock)
        return EventIntermediateTimerState(state['name'], delay, state['next'])

    def _parse_activity(self, state, emitters):
        emitter_name = state.get('emitter')
        dimensions = emitters[emitter_name] if emitter_name is not None else None
        variables_list = get_variables(state.get('variables', []), self.global_clock)
        return ActivityState(state['name'], dimensions, variables_list, state['next'])

    def _parse_event_start_message(self, state):
        variables_list = get_variables(state.get('variables', []), self.global_clock)
        return EventStartMessageState(state['name'], state['next'], variables_list)

    def _parse_subprocess_multi_variables(self, state):
        with open(state['states']) as f:
            child_config = json.load(f)
        child_emitters = {**self.emitters}
        child_emitters.update({e['name']: get_dimensions(e['dimensions'], self.global_clock)
                               for e in child_config.get('emitters', [])})
        child_states, _ = self._parse_states(child_config['states'], emitters=child_emitters)
        in_collection = [get_variables(item, self.global_clock) for item in state['items']]
        return SubprocessMultiVariablesState(state['name'], state['next'], child_states, in_collection)

    def _parse_states(self, state_desc_list, emitters=None):
        """Parse a list of state dicts into (states_dict, initial_state). emitters defaults to self.emitters."""
        if emitters is None:
            emitters = self.emitters
        states = {}
        initial_state = None
        for state in state_desc_list:
            name = state['name']
            state_type = state.get('type')
            if state_type is None:
                raise RuntimeError(f"State '{state.get('name', '?')}' is missing required field 'type'.")
            if state_type == 'activity':
                states[name] = self._parse_activity(state, emitters)
            elif state_type == 'event:end':
                states[name] = self._parse_event_end(state)
            elif state_type == 'event:start:timer':
                this_state = self._parse_event_start_timer(state)
                states[name] = this_state
                initial_state = this_state
            elif state_type == 'gateway:exclusive':
                states[name] = self._parse_gateway_exclusive(state)
            elif state_type == 'event:intermediate:timer':
                states[name] = self._parse_event_intermediate_timer(state)
            elif state_type == 'event:start:message':
                states[name] = self._parse_event_start_message(state)
            elif state_type == 'subprocess:multi:variables':
                states[name] = self._parse_subprocess_multi_variables(state)
            else:
                raise RuntimeError(f"Unknown state type: {state_type}")
        return states, initial_state

    def run_state_machine(self, states, variables, entry_state=None):
        current_state = entry_state if entry_state is not None else list(states.values())[0]
        while True:
            self.status_msg = f"Running, Sim Clock: {self.global_clock.now()}"
            next_name = current_state.execute(variables, self)
            if self.sim_control.is_done() or next_name is None:
                break
            current_state = states.get(next_name)
            if current_state is None:
                break

    def worker_thread(self):
        self.global_clock.activate_thread()
        self.run_state_machine(self.states, {})
        self.global_clock.end_thread()
        self.sim_control.remove_entity()

    def spawning_thread(self):
        self.global_clock.activate_thread()

        # Spawn the workers in a separate thread so we can stop the whole thing in the middle of spawning if necessary
        while not self.sim_control.is_done():
            multiplier = self.schedule.get_multiplier() if self.schedule else 1.0
            effective_max = max(1, int(self.max_entities * multiplier))
            if self.sim_control.get_entity_count() < effective_max:
                thread_name = 'W'+str(self.sim_control.get_entity_count())
                self.sim_control.add_entity()
                t = threading.Thread(target=self.worker_thread, name=thread_name, daemon=True)
                t.start()
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
        if self.header:
            self.target_printer.print(self.header)
        self.status_msg = f'Starting {self.type} job.'
        thread_name = 'Spawning'
        thrd = threading.Thread(target=self.spawning_thread, args=(), name=thread_name, daemon=True)
        thrd.start()
        thrd.join()

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
