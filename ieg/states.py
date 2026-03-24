import logging
import threading
import random
import time
import isodate

logger = logging.getLogger('ieg')

class Transition:
    # Represents a state transition in the state machine.
    # Defines the next state and the probability of transitioning to it.
    def __init__(self, next_state, probability):
        self.next_state = next_state
        self.probability = probability

    def __str__(self):
        return 'Transition(next_state='+str(self.next_state)+', probability='+str(self.probability)+')'

    @staticmethod
    def validate_desc(desc, context):
        """Validate a single transition config dict. Logs errors and returns bool."""
        valid = True
        if 'next' not in desc:
            logger.error("%s: transition missing required field 'next'", context)
            valid = False
        elif not isinstance(desc['next'], str):
            logger.error("%s: transition 'next' must be a string, got %s", context, type(desc['next']).__name__)
            valid = False
        if 'probability' not in desc:
            logger.error("%s: transition missing required field 'probability'", context)
            valid = False
        else:
            try:
                p = float(desc['probability'])
                if not (0 < p <= 1):
                    logger.error("%s: transition 'probability' must be in (0, 1], got %s", context, desc['probability'])
                    valid = False
            except (TypeError, ValueError):
                logger.error("%s: transition 'probability' must be a number, got %r", context, desc['probability'])
                valid = False
        return valid

    @staticmethod
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
    def __init__(self, name, dimensions, delay, transitions, variables, variables_on_entry=None):
        self.name = name
        self.dimensions = dimensions
        self.delay = delay
        self.transitions = transitions
        self.transistion_states = [t.next_state for t in transitions]
        self.transistion_probabilities = [t.probability for t in transitions]
        self.variables = variables
        self.variables_on_entry = variables_on_entry if variables_on_entry is not None else []

    def __str__(self):
        return 'State(name='+self.name+', dimensions='+str([str(d) for d in self.dimensions])+', delay='+str(self.delay)+', transistion_states='+str(self.transistion_states)+', transistion_probabilities='+str(self.transistion_probabilities)+'variables='+str([str(v) for v in self.variables])+')'

    @staticmethod
    def validate_desc(desc, emitter_names, context):
        """Validate a state config dict. Logs errors/warnings and returns bool."""
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'delay' not in desc:
            logger.error("%s: missing required field 'delay'", context)
            valid = False
        transitions = desc.get('transitions')
        if not transitions or not isinstance(transitions, list):
            logger.error("%s: 'transitions' required and must be a non-empty list", context)
            valid = False
        else:
            total_prob = 0.0
            for i, trans in enumerate(transitions):
                trans_ctx = f"{context}, transition [{i}]"
                if not Transition.validate_desc(trans, trans_ctx):
                    valid = False
                try:
                    total_prob += float(trans.get('probability', 0))
                except (TypeError, ValueError):
                    pass
            if abs(total_prob - 1.0) > 0.01:
                logger.warning(
                    "%s: transition probabilities sum to %.4f, not 1.0"
                    " — random.choices will normalise but this is likely a mistake",
                    context, total_prob
                )
                # do NOT set valid = False — this is non-fatal
        emitter = desc.get('emitter')
        if emitter is not None and emitter not in emitter_names:
            logger.error("%s: references emitter '%s' which is not defined in 'emitters'", context, emitter)
            valid = False
        return valid

    def get_next_state_name(self):
        return random.choices(self.transistion_states, weights=self.transistion_probabilities, k=1)[0]

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
