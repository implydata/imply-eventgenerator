# IEG classes and functions.

import json
import re
import os

from ieg.distributions import *
from ieg.targets import *
from ieg.dimensions import *
from ieg.states import *

# Additional modules.

from sortedcontainers import SortedList

# Standard modules.

from datetime import datetime, timedelta
import json
import threading
import time

# Update TEMPLATE_REGEX to capture optional strftime format
TEMPLATE_REGEX = re.compile(r"{{\s*([^|}]+)(?:\|([^}]+))?\s*}}")

def render_env_variables(config):
    """
    Replace placeholders in the configuration with environment variable values.
    Placeholders should be in the format %VARIABLE_NAME%.
    """
    if isinstance(config, dict):
        return {k: render_env_variables(v) for k, v in config.items()}
    elif isinstance(config, str):
        return re.sub(r"%(\w+)%", lambda match: os.getenv(match.group(1), match.group(0)), config)
    else:
        return config

class FutureEvent:
    # Represents a future event in the simulation clock.
    # Each event has a timestamp and can be paused or resumed.
    # Used by the Clock class to manage simulated time.
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
        #print(self.name+" pausing")
        self.event.clear()
        self.event.wait()
    def resume(self):
        #print(self.name+" resuming")
        self.event.set()

class Clock:
    # Simulates time for the data generation process.
    # Supports both real-time and simulated time modes.
    # Manages future events and thread synchronization.
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

    def get_duration(self) :
        time_delta = self.now() - self.start_time
        return time_delta.total_seconds()

    def get_start_time(self):
        return self.start_time

    def activate_thread(self):
        if self.time_type != 'REAL':
            self.lock.acquire()
            self.active_threads += 1
            self.lock.release()

    def deactivate_thread(self):
        if self.time_type != 'REAL':
            self.lock.acquire()
            self.active_threads -= 1
            self.lock.release()

    def end_thread(self):
        if self.time_type != 'REAL':
            self.lock.acquire()
            self.active_threads -= 1
            if len(self.future_events) > 0:
                self.remove_event().resume()
            self.lock.release()

    def release_all(self):
        if self.time_type != 'REAL':
            self.lock.acquire()
            #print('release_all - active_threads = '+str(self.active_threads))
            for e in self.future_events:
                e.resume()
            self.lock.release()

    def add_event(self, future_t):
        this_event = FutureEvent(future_t)
        self.future_events.add(this_event)
        #print('add_event (after) '+threading.current_thread().name+' - '+str(self))
        return this_event

    def remove_event(self):
        #print('remove_event (before) '+threading.current_thread().name+' - '+str(self))
        next_event = self.future_events[0]
        self.future_events.remove(next_event)
        return next_event

    def pause(self, event):
        self.active_threads -= 1
        self.lock.release()
        event.pause()
        self.lock.acquire()
        self.active_threads += 1

    def resume(self, event):
        event.resume()

    def now(self) -> datetime:
        if self.time_type != 'REAL':
            t = self.sim_time
        else:
            t = datetime.now()
        return t

    def sleep(self, delta):
        # Cannot travel to the past, so don't move the time if delta is negative
        if delta < 0:
            return
        if self.time_type != 'REAL': # Simulated time
            self.lock.acquire()
            #print(threading.current_thread().name+" begin sleep "+str(self.sim_time)+" + "+str(delta))
            this_event = self.add_event(self.sim_time + timedelta(seconds=delta))
            #print(threading.current_thread().name+" active threads "+str(self.active_threads))
            if self.active_threads == 1:
                next_event = self.remove_event()
                if str(this_event) != str(next_event):
                    self.resume(next_event)
                    #print(threading.current_thread().name+" start pause if")
                    self.pause(this_event)
                    #print(threading.current_thread().name+" end pause if")
            else:
                #print(threading.current_thread().name+" start pause else")
                self.pause(this_event)
                #print(threading.current_thread().name+" end pause else")
            self.sim_time = this_event.get_time()
            self.lock.release()
            # if new time is past current time and the simulation is SIM_REAL, switch to REAL and continue in real-time
            if self.time_type == 'SIM_TO_REAL' and self.sim_time > datetime.now():
                self.time_type = 'REAL'
                self.sim_time = datetime.now()
        else: # Real time
            time.sleep(delta)

class DataDriver:
    # Main driver class for generating data.
    # Handles configuration, state machine, and output targets.

    def __init__(self, name, config, target, runtime, total_recs, time_type, start_time, max_entities, record_format):
        self.name = name
        self.config = config
        self.runtime = runtime
        self.total_recs = total_recs
        self.time_type = time_type
        self.start_time = start_time
        self.max_entities = max_entities
        self.status_msg = 'Creating...'
        self.record_format = record_format

        if self.record_format:
            self.record_format = render_env_variables(record_format)

        #
        # Set up the global clock
        #

        self.global_clock = Clock(time_type, start_time)
        self.sim_control = Controller(total_recs, runtime, self.global_clock)

        #
        # Set up the output target
        #

        self.target = target
        if target['type'].lower() == 'stdout':
            self.target_printer = TargetStdout()
        elif target['type'].lower() == 'file':
            path = target['path']
            if path is None:
                msg = 'Error: File target requires a path item'
                raise Exception(msg)
            self.target_printer = TargetFile(path)
        elif target['type'].lower() == 'kafka':
            if 'endpoint' in target.keys():
                endpoint = target['endpoint']
            else:
                msg = 'Error: Kafka target requires an endpoint item'
                raise Exception(msg)
            if 'topic' in target.keys():
                topic = target['topic']
            else:
                msg = 'Error: Kafka target requires a topic item'
                raise Exception(msg)
            if 'security_protocol' in target.keys():
                security_protocol = target['security_protocol']
            else:
                security_protocol = 'PLAINTEXT'
            if 'compression_type' in target.keys():
                compression_type = target['compression_type']
            else:
                compression_type = None
            if 'topic_key' in target.keys():
                topic_key = target['topic_key']
            else:
                topic_key = []
            self.target_printer = TargetKafka(endpoint, topic, security_protocol, compression_type, topic_key)
        elif target['type'].lower() == 'confluent':
            if 'servers' in target.keys():
                servers = target['servers']
            else:
                msg = 'Error: Confluent target requires a servers item'
                raise Exception(msg)
            if 'topic' in target.keys():
                topic = target['topic']
            else:
                msg = 'Error: Confluent target requires a topic item'
                raise Exception(msg)
            if 'username' in target.keys():
                username = target['username']
            else:
                msg = 'Error: Confluent target requires a username'
                raise Exception(msg)
            if 'password' in target.keys():
                password = target['password']
            else:
                msg = 'Error: Confluent target requires a password'
                raise Exception(msg)
            if 'topic_key' in target.keys():
                topic_key = target['topic_key']
            else:
                topic_key = []
            self.target_printer = TargetConfluent(servers, topic, username, password, topic_key)
        else:
            msg = 'Error: Unknown target type "'+target['type']+'"'
            raise Exception(msg)

        # Remove type validation and default to generator
        self.type = 'generator'

        # Set up the interarrival rate
        rate = self.config['interarrival']
        self.rate_delay = parse_distribution(rate)

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

        for state in self.states.values():
            for next_state_name in state.transitions.keys():
                if next_state_name.lower() != 'stop' and next_state_name not in self.states:
                    raise RuntimeError(f"State '{next_state_name}' referenced in transitions but not defined in state machine.")

        for state in state_desc:
            name = state['name']
            emitter_name = state['emitter']
            if 'variables' not in state.keys():
                variables = []
            else:
                variables = get_variables(state['variables'], self.global_clock)
            dimensions = self.emitters[emitter_name]
            delay = parse_distribution(state['delay'])
            transitions = Transition.parse_transitions(state['transitions'])
            this_state = State(name, dimensions, delay, transitions, variables)
            self.states[name] = this_state
            if self.initial_state is None:
                self.initial_state = this_state

    @staticmethod
    def get_value(record, key, default=""):
        """
        Retrieve the value for a given key from the record dictionary.
        Supports nested keys using dot notation (e.g., "field.subfield").
        Returns the default value if the key is missing.
        """
        keys = key.split(".")  # Split the key by dots for nested access
        value = record
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default  # Return default if key is missing
        return value

    def render_template(self, template, record):
        """
        Replace placeholders in the template with values from the record.
        Supports optional strftime formatting for datetime values.
        """
        def replace_placeholder(match):
            key = match.group(1)  # Placeholder name (e.g., "time")
            format_str = match.group(2)  # Optional strftime format (e.g., "%Y-%m-%d")
            value = self.get_value(record, key)  # Retrieve the value from the record

            if isinstance(value, datetime) and format_str:
                try:
                    return value.strftime(format_str)  # Apply strftime if format is provided
                except ValueError as e:
                    raise ValueError(f"Invalid strftime format '{format_str}' for key '{key}': {e}")
            return str(value) if value is not None else ''  # Default to string conversion

        return TEMPLATE_REGEX.sub(replace_placeholder, template)

    def apply_pattern(self, pattern, record):
        if isinstance(pattern, dict):
            return {k: self.apply_pattern(v, record) for k, v in pattern.items()}
        elif isinstance(pattern, str):
            return self.render_template(pattern, record)
        else:
            return pattern

    def render_record(self, record):
        if not self.record_format:
            # If no record format is provided, return the record as a JSON string.
            for key, value in record.items():
                if isinstance(value, datetime):
                    record[key] = value.isoformat()
            return json.dumps(record)

        try:
            # Apply the pattern using the new approach
            formatted_record = self.apply_pattern(self.record_format, record)
        except Exception as e:
            raise ValueError(f"Error formatting record with pattern: {e}")
        return formatted_record

    def create_record(self, dimensions, variables):
        record = {}
        for element in dimensions:
            if isinstance(element, DimensionVariable):
                record[element.name] = variables[element.variable_name]
            else:
                if isinstance(element, DimensionTimestampClock) or not element.is_missing():
                    record[element.name] = element.get_stochastic_value()
        return record

    def set_variable_values(self, variables, dimensions):
        for d in dimensions:
            variables[d.name] = d.get_stochastic_value()

    def worker_thread(self):
        # Processes the state machine using worker threads.
        # Generates records and sends them to the output target.
        #print('Thread '+threading.current_thread().name+' starting...')
        self.global_clock.activate_thread()
        current_state = self.initial_state
        variables = {}
        while True:
            self.set_variable_values(variables, current_state.variables)
            record = self.create_record(current_state.dimensions, variables)
            formatted_record = self.render_record(record)  # Format the record here
            self.target_printer.print(formatted_record)  # Pass the formatted record to the target printer
            self.sim_control.inc_rec_count()
            if self.sim_control.is_done():
                break
            delta = float(current_state.delay.get_sample())
            #self.status_msg=f"Thread sleeping {delta} seconds. Sim Clock: {self.global_clock.now()}"
            self.global_clock.sleep(delta)
            self.status_msg=f"Running, Sim Clock: {self.global_clock.now()}"
            if self.sim_control.is_done():
                break
            next_state_name = current_state.get_next_state_name()
            if next_state_name.lower() == 'stop':
                break
            current_state = self.states[next_state_name]

        #print('Thread '+threading.current_thread().name+' done!')
        self.global_clock.end_thread()
        self.sim_control.remove_entity()

    def spawning_thread(self):
        # Spawns worker threads to generate records concurrently.
        self.global_clock.activate_thread()

        # Spawn the workers in a separate thread so we can stop the whole thing in the middle of spawning if necessary
        while not self.sim_control.is_done():
            if (self.sim_control.get_entity_count() < self.max_entities):
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
            return self.global_clock.now().strftime('%Y-%m-%d %H:%M:%S.%f')

    def simulate(self):
        # Starts the simulation based on the configuration.
        self.status_msg = f'Starting {self.type} job.'
        thread_name = 'Spawning'
        thrd = threading.Thread(target=self.spawning_thread, args=(), name=thread_name, daemon=True)
        thrd.start()
        thrd.join()

    def terminate(self):
        # Terminates the simulation.
        self.sim_control.terminate()

    def report(self):
        # Generates a report of the simulation status and statistics.
        return {  'name': self.name,
                  'config_file': self.config['config_file'],
                  'target': self.target,
                  'active_sessions': self.sim_control.get_entity_count(),
                  'total_records': self.sim_control.get_record_count(),
                  'start_time': self.sim_control.get_start_time().strftime('%Y-%m-%d %H:%M:%S'),
                  'run_time': self.sim_control.get_duration(),
                  'status' : 'COMPLETE' if self.sim_control.is_done() else 'RUNNING',
                  'status_msg' : self.status_msg
                }
