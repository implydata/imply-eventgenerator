# IEG classes and functions.

from ieg.distributions import (
    parse_distribution
)

from ieg.targets import (
    TargetStdout,
    TargetFile,
    TargetKafka,
    TargetConfluent
)

from ieg.dimensions import (
    DimensionStringTime,
    DimensionVariable,
    get_dimensions,
    get_variables
)

# Additional modules.

from confluent_kafka import Producer
from kafka import KafkaProducer
from sortedcontainers import SortedList
import numpy as np

# Standard modules.

from datetime import datetime, timedelta
import json
import random
import threading
import time

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

class Transition:
    # Represents a state transition in the state machine.
    # Defines the next state and the probability of transitioning to it.
    def __init__(self, next_state, probability):
        self.next_state = next_state
        self.probability = probability

    def __str__(self):
        return 'Transition(next_state='+str(self.next_state)+', probability='+str(self.probability)+')'

def parse_transitions(desc):
    transitions = []
    for trans in desc:
        next_state = trans['next']
        probability = float(trans['probability'])
        transitions.append(Transition(next_state, probability))
    return transitions

class State:
    # Represents a state in the state machine.
    # Defines dimensions, delay, transitions, and variables for the state.
    def __init__(self, name, dimensions, delay, transitions, variables):
        self.name = name
        self.dimensions = dimensions
        self.delay = delay
        self.transistion_states = [t.next_state for t in transitions]
        self.transistion_probabilities = [t.probability for t in transitions]
        self.variables = variables

    def __str__(self):
        return 'State(name='+self.name+', dimensions='+str([str(d) for d in self.dimensions])+', delay='+str(self.delay)+', transistion_states='+str(self.transistion_states)+', transistion_probabilities='+str(self.transistion_probabilities)+'variables='+str([str(v) for v in self.variables])+')'

    def get_next_state_name(self):
        return random.choices(self.transistion_states, weights=self.transistion_probabilities, k=1)[0]

class SimEnd:
    # Manages the simulation end conditions.
    # Tracks the total records generated and runtime duration.
    def __init__(self, total_recs, runtime, global_clock):
        self.lock = threading.Lock()
        self.thread_end_event = threading.Event()
        self.total_recs = total_recs
        self.record_count = 0
        self.global_clock = global_clock
        self.entity_count = 0
        if runtime is None:
            self.t = None
        else:
            if runtime[-1].lower() == 's':
                self.t = int(runtime[:-1])
            elif runtime[-1].lower() == 'm':
                self.t = int(runtime[:-1]) * 60
            elif runtime[-1].lower() == 'h':
                self.t = int(runtime[:-1]) * 60 * 60
            else:
                msg = 'Error: Unknown runtime value"'+runtime+'"'
                raise Exception(msg)

    def get_entity_count(self):
        return self.entity_count

    def add_entity(self):
        self.lock.acquire()
        self.entity_count +=1
        self.lock.release()

    def remove_entity(self):
        self.lock.acquire()
        self.entity_count -=1
        self.lock.release()

    def inc_rec_count(self):
        self.lock.acquire()
        self.record_count += 1
        self.lock.release()
        if (self.total_recs is not None) and (self.record_count >= self.total_recs):
            self.thread_end_event.set()

    def is_done(self):
        return ((self.total_recs is not None) and (self.record_count >= self.total_recs)) \
                or ((self.t is not None) and ((self.get_duration() > self.t) or self.thread_end_event.is_set()))

    def wait_for_end(self):
        if self.t is not None:
            self.global_clock.activate_thread()
            self.global_clock.sleep(self.t)
            self.thread_end_event.set()
            self.global_clock.deactivate_thread()
        elif self.total_recs is not None:
            self.thread_end_event.wait()
            self.global_clock.release_all()
        else:
            while True:
                time.sleep(60)

    def get_duration(self):
        return self.global_clock.get_duration()

    def get_start_time(self):
        return self.global_clock.get_start_time()

    def get_record_count(self):
        return self.record_count;

    def terminate(self):
        if self.total_recs is not None:
            self.record_count = self.total_recs
        self.thread_end_event.set()


class DataDriver:
    # Main driver class for generating data.
    # Handles configuration, state machine, and output targets.

    def __init__(self, name, config, target, runtime, total_recs, time_type, start_time, max_entities, global_pattern):
        self.name = name
        self.config = config
        self.runtime = runtime
        self.total_recs = total_recs
        self.time_type = time_type
        self.start_time = start_time
        self.max_entities = max_entities
        self.status_msg = 'Creating...'

        # Validate the global pattern
        self.global_pattern = global_pattern
        if self.global_pattern:
            available_fields = {"time"}  # "time" is always emitted
            for emitter in self.config.get("emitters", []):
                for dimension in emitter.get("dimensions", []):
                    available_fields.add(dimension["name"])
            try:
                # Use a dummy dictionary with available fields to test the pattern
                dummy_record = {field: "" for field in available_fields}
                self.global_pattern.format(**dummy_record)
            except KeyError as e:
                raise KeyError(f"Global pattern references an unknown field: {e}. Ensure all fields in the pattern are defined in the emitters or are default fields.")
            except ValueError as e:
                raise ValueError(f"Invalid global pattern: {e}. Check for mismatched or invalid format strings.")

        #
        # Set up the global clock
        #

        self.global_clock = Clock(time_type, start_time)
        self.sim_control = SimEnd(total_recs, runtime, self.global_clock)

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

        # A different source of data generation is a digital twin mode
        # A source file is used that already contains a sequence of events for a given time period
        # The source file is expected to be sorted on time
        # time field mapping is needed and uses a json path to specify it with either 'millis' or ISO time format specified
        # This generator will
        # - read the first line in the file to find the starting timestamp and save that
        # - it will then emit events with the generator time such that the events have the same cadence as the original file
    
        self.type='generator'
        if 'type' in config.keys():
            self.type=config['type']

        if self.type=='replay':        
            if 'source_file' in config.keys():
                self.replay_file = config['source_file']
            else:
                msg='Error: "type" = `replay` requires a "source_file".'
                raise Exception(msg)
            if 'source_format' in config.keys():
                self.source_format = config['source_format']
            else:
                self.source_format = 'csv' # default to csv as it is the only supported format for now

            if 'time_field' in config.keys():
                self.time_field = config['time_field']
            else:
                msg = 'Error: "type" = `replay` requires a the specification of a "time_field".'
                raise Exception(msg)
            if 'time_format' in config.keys():
                self.time_format = config['time_format']
            else:
                print('Info: time_format was not specified, using default "%Y-%m-%d %H:%M:%S" which is for timestamps in the form "YYYY-MM-DD hh:mm:ss". See https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes for accepted format values.')
                self.time_format = '%Y-%m-%d %H:%M:%S'
            if 'null_injection' in config.keys():
                self.do_null_injection = True
                self.null_injections = config['null_injection']
                msg = 'Error: "null_injection" must be an array in the form: [{"field":"field1","null_probability":0.05},{"field":"field2", "null_probability":0.01}].'
                if not isinstance(self.null_injections, list):
                    raise Exception(msg)
                else:
                    for injection in self.null_injections:
                        if not isinstance(injection, dict) or 'field' not in injection.keys() or 'null_probability' not in injection.keys():
                            raise Exception(msg)
            else:
                self.do_null_injection = False
            if 'time_skipping' in config.keys():
                self.do_time_skips = True
                self.time_skip_config = config['time_skipping']
                if not isinstance(self.time_skip_config, dict) \
                    or 'skip_probability' not in self.time_skip_config.keys() \
                    or 'min_skip_duration' not in self.time_skip_config.keys() \
                    or 'max_skip_duration' not in self.time_skip_config.keys():
                    msg='Error: "time_skipping" must have the form: {"skip_probability": 0.01, "min_skip_duration": 5, "max_skip_duration": 300}"'
                    raise Exception(msg)
            else:
                self.do_time_skips = False

        elif self.type=='generator':
            #
            # Set up the interarrival rate
            #
            self.type='generator'
            rate = self.config['interarrival']
            self.rate_delay = parse_distribution(rate)

            #
            # Set up emitters list
            #
            self.emitters = {}
            for emitter in self.config['emitters']:
                name = emitter['name']
                dimensions = get_dimensions(emitter['dimensions'], self.global_clock)
                self.emitters[name] = dimensions

            #
            # Set up the state machine
            #
            state_desc = self.config['states']
            self.initial_state = None
            self.states = {}
            for state in state_desc:
                name = state['name']
                emitter_name = state['emitter']
                if 'variables' not in state.keys():
                    variables = []
                else:
                    variables = get_variables(state['variables'])
                dimensions = self.emitters[emitter_name]
                delay = parse_distribution(state['delay'])
                transitions = parse_transitions(state['transitions'])
                this_state = State(name, dimensions, delay, transitions, variables)
                self.states[name] = this_state
                if self.initial_state == None:
                    self.initial_state = this_state
        else:
            msg = f"Error: Unknown `type` = {self.type}."
            raise Exception(msg)        

    def format_record_with_pattern(self, record):
        """
        Apply the global pattern to the record if a pattern is defined.
        """
        
        if not self.global_pattern:
            return json.dumps(record)  # Default to JSON if no pattern is provided

        try:
            # Use Python string formatting with `{key}` placeholders
            # TODO: Support full Pythonic formatting with `{key:format}` placeholders.
            formatted_record = self.global_pattern.format(**record)
        except KeyError as e:
            raise KeyError(f"Missing key in record for pattern: {e}")
        except ValueError as e:
            raise ValueError(f"Error formatting record with pattern: {e}")
        return formatted_record

    def create_record(self, dimensions, variables):
        """
        Create a record by collecting values from dimensions and applying the global pattern.
        """
        record = {}
        for element in dimensions:
            if isinstance(element, DimensionVariable):
                # Fetch the value from the variables dictionary
                record[element.name] = variables[element.variable_name]
            else:
                if isinstance(element, DimensionStringTime) or not element.is_missing():
                    record[element.name] = element.get_stochastic_value()

        # Apply the global pattern to the record
        return self.format_record_with_pattern(record)

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
            self.target_printer.print(record)  # Pass the formatted record to the target printer
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

    def parse_time_from_record(self, json_obj, time_field, time_format) -> datetime:
        if time_format == 'millis':
            return datetime.fromtimestamp(float(json_obj[time_field])/1000.0)
        elif time_format == 'seconds' or time_format == 'epoch' or time_format == 'posix':
            return datetime.fromtimestamp(float(json_obj[time_field]))
        elif time_format == 'nanos':
            return datetime.fromtimestamp(float(json_obj[time_field])/1000000.0)
        else:
            return datetime.strptime(json_obj[time_field], time_format)

    def get_new_time_for_record(self):
            return self.global_clock.now().strftime('%Y-%m-%d %H:%M:%S.%f')

    def replay_thread(self):
        # Processes a replay file to generate events based on the global clock.
        # Supports null injection and time skipping.
        # process replay file, generate events based on global clock
        # read the source file
        import json
        import csv
        import copy
        import random

        self.global_clock.activate_thread()

        data = []
        self.status_msg = f"Reading data from file {self.replay_file}..."
        with open(self.replay_file, 'r') as csvfile:
            for line in csv.DictReader(csvfile):
                data.append(line)
        total_source_recs = len(data)
        cycle = 0
        self.status_msg = f"Read {total_source_recs} rows from file... sim control is done = {self.sim_control.is_done()}"
        sim_start_time = self.global_clock.now()
        while not self.sim_control.is_done():
            cycle += 1
            self.status_msg =  f"Generating data, cycle:{cycle} with max of {total_source_recs} messages per cycle."
            i = 0 # start each cycle through from the beginning of the replay event sequence
            while i < total_source_recs:
                current_source_time = self.parse_time_from_record( data[i], self.time_field, self.time_format)
                json_obj = copy.deepcopy(data[i])
                # reset time on the output object to simulated time
                json_obj[self.time_field]=self.get_new_time_for_record()
                self.status_msg =  f"Replaying: Cycle:{cycle} msg:{i} - Sim clock:{json_obj[self.time_field]}."
                #do null injections if configured
                if self.do_null_injection:
                    for nuller in self.null_injections:
                        if random.random()<nuller['null_probability']:
                            json_obj[nuller['field']] = None
                # print record to defined target
                record = json.dumps(json_obj)
                self.target_printer.print(record)
                self.sim_control.inc_rec_count()
                i += 1 # move to next event in the replay set
                if i < total_source_recs:
                    next_source_time = self.parse_time_from_record( data[i], self.time_field, self.time_format)
                    if self.do_time_skips and random.random()<self.time_skip_config['skip_probability']:
                        # calculate skip time in seconds
                        skip_time = random.uniform(self.time_skip_config['min_skip_duration'], self.time_skip_config['max_skip_duration'])
                        self.status_msg =  f"Replaying: Cycle:{cycle} msg:{i} - Sim clock:{json_obj[self.time_field]}. Skipping {skip_time} seconds."
                        # find the next event in the sequence that is after the skip time
                        while ((next_source_time - current_source_time).total_seconds() < skip_time) and (i < total_source_recs-1):
                            i += 1
                            next_source_time = self.parse_time_from_record( data[i], self.time_field, self.time_format)
                            self.status_msg =  f"Replaying: Cycle:{cycle} msg:{i} - Sim clock:{json_obj[self.time_field]}. Skipping {skip_time} seconds."
                    # advance time according to the elapsed time between events in the replay file
                    self.global_clock.sleep(float((next_source_time - current_source_time).total_seconds()))
                if self.sim_control.is_done():
                    break
        self.global_clock.end_thread()

    def simulate(self):
        # Starts the simulation based on the configuration.
        self.status_msg=f'Starting {self.type} job.'
        if self.type == 'replay':
            # run a single replay thread, no data generation needed except for new timestamps
            thread_name = 'DigitalTwinSimulator'
            self.sim_control.add_entity()
            thrd = threading.Thread(target=self.replay_thread, name=thread_name, daemon=True)
            thrd.start()
        else:
            thrd = threading.Thread(target=self.spawning_thread, args=(), name='Spawning', daemon=True)
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
