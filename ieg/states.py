"""State machine classes. See docs/states.md."""

import logging
import threading
import random
import time
import isodate

logger = logging.getLogger('ieg')

class StateBase:
    """Abstract base for all state types."""

    type = None  # set as a class attribute on each subclass

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f'{self.__class__.__name__}(name={self.name})'

    def execute(self, variables, context):
        """Perform this state's behaviour and return the name of the next state (or None to terminate)."""
        raise NotImplementedError


class EventEndState(StateBase):
    type = 'event:end'

    def execute(self, variables, context):
        logger.debug("Thread %s reached event:end", threading.current_thread().name)
        return None


class EventStartTimerState(StateBase):
    type = 'event:start:timer'

    def __init__(self, name, next_state):
        super().__init__(name)
        self.next_state = next_state

    def execute(self, variables, context):
        logger.debug("Thread %s starting process instance", threading.current_thread().name)
        return self.next_state


class EventStartMessageState(StateBase):
    type = 'event:start:message'

    def __init__(self, name, next_state, variables):
        super().__init__(name)
        self.next_state = next_state
        self.variables = variables

    def execute(self, variables, context):
        for d in self.variables:
            variables[d.name] = d.get_stochastic_value()
        logger.debug("Thread %s starting process instance", threading.current_thread().name)
        return self.next_state


class EventIntermediateTimerState(StateBase):
    type = 'event:intermediate:timer'

    def __init__(self, name, delay, next_state):
        super().__init__(name)
        self.delay = delay
        self.next_state = next_state

    def execute(self, variables, context):
        delta = float(self.delay.get_sample())
        context.global_clock.sleep(delta)
        return self.next_state


class ActivityState(StateBase):
    type = 'activity'

    def __init__(self, name, dimensions, variables, next_state):
        super().__init__(name)
        self.dimensions = dimensions
        self.variables = variables
        self.next_state = next_state

    def execute(self, variables, context):
        for d in self.variables:
            variables[d.name] = d.get_stochastic_value()
        if self.dimensions is not None:
            record = context.create_record(self.dimensions, variables)
            context.target_printer.print(context.render_record(record))
            context.sim_control.inc_rec_count()
        return self.next_state


class GatewayExclusiveState(StateBase):
    type = 'gateway:exclusive'

    def __init__(self, name, next_states, probabilities):
        super().__init__(name)
        self.next_states = next_states
        self.probabilities = probabilities

    def execute(self, variables, context):
        return random.choices(self.next_states, weights=self.probabilities, k=1)[0]


class SubprocessMultiVariablesState(StateBase):
    type = 'subprocess:multi:variables'

    def __init__(self, name, next_state, sub_states, in_collection):
        super().__init__(name)
        self.next_state = next_state
        self.sub_states = sub_states
        self.in_collection = in_collection

    def execute(self, variables, context):
        msg_start = next(
            (s for s in self.sub_states.values() if isinstance(s, EventStartMessageState)),
            None
        )
        if msg_start is None:
            raise RuntimeError(
                f"subprocess:multi:variables '{self.name}': child config has no "
                "'event:start:message' state. Configs designed for subprocess use must "
                "declare an 'event:start:message' entry point."
            )
        for item_vars in self.in_collection:
            for d in item_vars:
                variables[d.name] = d.get_stochastic_value()
            context.run_state_machine(self.sub_states, variables, entry_state=msg_start)
        return self.next_state


class Controller:
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
            try:
                self.t = isodate.parse_duration(runtime).total_seconds()
            except Exception as e:
                raise ValueError(f"Error parsing runtime '{runtime}': {e}")

    def get_entity_count(self):
        return self.entity_count

    def add_entity(self):
        self.lock.acquire()
        self.entity_count += 1
        self.lock.release()

    def remove_entity(self):
        self.lock.acquire()
        self.entity_count -= 1
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
        return self.record_count

    def terminate(self):
        if self.total_recs is not None:
            self.record_count = self.total_recs
        self.thread_end_event.set()
