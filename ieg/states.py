"""State machine classes: Transition, State, and Controller.

State models one node in the Actor lifecycle graph. Controller tracks simulation
end conditions (record count or elapsed duration). Transition encodes a single
weighted edge in a gateway:exclusive state's transitions list.

See docs/states.md for the config-level reference.
"""

import itertools
import logging
import random
import threading

import isodate

logger = logging.getLogger('ieg')

class Transition:
    """A single weighted edge in a gateway:exclusive state's transitions list."""
    def __init__(self, next_state, probability):
        self.next_state = next_state
        self.probability = probability

    def __str__(self):
        return (
            'Transition(next_state=' + str(self.next_state)
            + ', probability=' + str(self.probability) + ')'
        )

    @staticmethod
    def validate_desc(desc, context):
        """Validate a single transition config dict. Logs errors and returns bool."""
        valid = True
        if 'next' not in desc:
            logger.error("%s: transition missing required field 'next'", context)
            valid = False
        elif not isinstance(desc['next'], str):
            logger.error(
                "%s: transition 'next' must be a string, got %s",
                context, type(desc['next']).__name__
            )
            valid = False
        if 'probability' not in desc:
            logger.error("%s: transition missing required field 'probability'", context)
            valid = False
        else:
            try:
                p = float(desc['probability'])
                if not (0 < p <= 1):
                    logger.error(
                        "%s: transition 'probability' must be in (0, 1], got %s",
                        context, desc['probability']
                    )
                    valid = False
            except (TypeError, ValueError):
                logger.error(
                    "%s: transition 'probability' must be a number, got %r",
                    context, desc['probability']
                )
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

VALID_TYPES = {
    'activity', 'gateway:exclusive', 'event:start:timer',
    'event:intermediate:timer', 'event:end'
}

class State:
    """A node in the Actor lifecycle state machine.

    type determines runtime behaviour:
      event:start:timer        — controls worker spawn pacing; always first
      event:intermediate:timer — advances the clock without emitting
      activity                 — evaluates variables and optionally emits a record
      gateway:exclusive        — routes to one of several next states by probability
      event:end                — terminates the worker thread
    """
    def __init__(self, name, state_type, dimensions, delay, transitions, variables):
        self.name = name
        self.type = state_type
        self.dimensions = dimensions
        self.delay = delay
        self.transitions = transitions
        self.transition_states = [t.next_state for t in transitions]
        self.transition_probabilities = [t.probability for t in transitions]
        # random.choices(weights=...) recomputes this cumulative sum from
        # scratch on every single call — precompute it once, since the
        # probabilities never change after construction.
        self._transition_cum_weights = list(
            itertools.accumulate(self.transition_probabilities)
        )
        self.variables = variables

    def __str__(self):
        return (
            'State(name=' + self.name + ', type=' + self.type
            + ', dimensions=' + str([str(d) for d in self.dimensions])
            + ', delay=' + str(self.delay)
            + ', transition_states=' + str(self.transition_states)
            + ', transition_probabilities=' + str(self.transition_probabilities)
            + 'variables=' + str([str(v) for v in self.variables]) + ')'
        )

    @staticmethod
    def validate_desc(desc, emitter_names, context):
        """Validate a state config dict. Logs errors/warnings and returns bool."""
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False

        state_type = desc.get('type')
        if state_type is None:
            logger.error("%s: missing required field 'type'", context)
            return False
        if state_type not in VALID_TYPES:
            logger.error("%s: unknown state type '%s'", context, state_type)
            return False  # nothing else meaningful to check

        if state_type == 'event:end':
            if desc.get('emitter') is not None:
                logger.error("%s: event:end must not have an emitter", context)
                valid = False
            if 'variables' in desc or 'variables_on_entry' in desc:
                logger.error(
                    "%s: event:end must not have variables — only activities "
                    "can set variables", context
                )
                valid = False
            return valid

        if state_type == 'event:start:timer':
            if 'cardinality_distribution' not in desc:
                logger.error(
                    "%s: event:start:timer missing required field "
                    "'cardinality_distribution'", context
                )
                valid = False
            if desc.get('emitter') is not None:
                logger.error("%s: event:start:timer must not have an emitter", context)
                valid = False
            if 'next' not in desc:
                logger.error(
                    "%s: event:start:timer missing required field 'next'", context
                )
                valid = False
            elif not isinstance(desc['next'], str):
                logger.error("%s: event:start:timer 'next' must be a string", context)
                valid = False
            if 'transitions' in desc:
                logger.error(
                    "%s: event:start:timer uses 'next', not 'transitions'", context
                )
                valid = False
            if 'variables' in desc or 'variables_on_entry' in desc:
                logger.error(
                    "%s: event:start:timer must not have variables — only "
                    "activities can set variables", context
                )
                valid = False
            return valid

        if state_type == 'event:intermediate:timer':
            if 'cardinality_distribution' not in desc:
                logger.error(
                    "%s: event:intermediate:timer missing required field "
                    "'cardinality_distribution'", context
                )
                valid = False
            if 'next' not in desc:
                logger.error(
                    "%s: event:intermediate:timer missing required field 'next'",
                    context
                )
                valid = False
            elif not isinstance(desc['next'], str):
                logger.error(
                    "%s: event:intermediate:timer 'next' must be a string", context
                )
                valid = False
            if desc.get('emitter') is not None:
                logger.error(
                    "%s: event:intermediate:timer must not have an emitter", context
                )
                valid = False
            if 'transitions' in desc:
                logger.error(
                    "%s: event:intermediate:timer uses 'next', not 'transitions'",
                    context
                )
                valid = False
            if 'variables' in desc or 'variables_on_entry' in desc:
                logger.error(
                    "%s: event:intermediate:timer must not have variables — "
                    "only activities can set variables", context
                )
                valid = False
            return valid

        if state_type == 'activity':
            if 'cardinality_distribution' in desc:
                logger.error(
                    "%s: activity must not have 'cardinality_distribution' — "
                    "precede it with event:intermediate:timer", context
                )
                valid = False
            if 'transitions' in desc:
                logger.error(
                    "%s: activity uses 'next', not 'transitions' — add a "
                    "gateway:exclusive for routing", context
                )
                valid = False
            if 'next' not in desc:
                logger.error("%s: activity missing required field 'next'", context)
                valid = False
            elif not isinstance(desc['next'], str):
                logger.error("%s: activity 'next' must be a string", context)
                valid = False
            if 'variables_on_entry' in desc:
                logger.error(
                    "%s: 'variables_on_entry' is not supported — use "
                    "'variables' in an activity", context
                )
                valid = False
            emitter = desc.get('emitter')
            if emitter is not None and emitter not in emitter_names:
                logger.error(
                    "%s: references emitter '%s' which is not defined in 'emitters'",
                    context, emitter
                )
                valid = False
            return valid

        if state_type == 'gateway:exclusive':
            if desc.get('emitter') is not None:
                logger.error("%s: gateway:exclusive must not have an emitter", context)
                valid = False
            if 'cardinality_distribution' in desc:
                logger.error(
                    "%s: gateway:exclusive must not have 'cardinality_distribution'",
                    context
                )
                valid = False
            if 'next' in desc:
                logger.error(
                    "%s: gateway:exclusive uses 'transitions', not 'next'", context
                )
                valid = False
            if 'variables' in desc or 'variables_on_entry' in desc:
                logger.error(
                    "%s: gateway:exclusive must not have variables — only "
                    "activities can set variables", context
                )
                valid = False
            transitions = desc.get('transitions')
            if not transitions or not isinstance(transitions, list):
                logger.error(
                    "%s: gateway:exclusive missing required field 'transitions'",
                    context
                )
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
                    logger.error(
                        "%s: transition probabilities sum to %.4f, not 1.0",
                        context, total_prob
                    )
                    valid = False
            return valid

        return valid

    def get_next_state_name(self):
        if not self.transition_states:
            return None
        return random.choices(
            self.transition_states, cum_weights=self._transition_cum_weights, k=1
        )[0]

def estimate_session_length(states, start_state):
    """Estimate how long a typical session lasts, from the state graph alone.

    Walks the graph once from start_state, weighting each transition by its
    probability and summing event:intermediate:timer means, but stops following
    any branch that revisits a state already seen on that path -- so a loop
    contributes only its first pass (`naive`). Separately tracks the probability
    of reaching event:end without ever looping back (`p_escape`). Dividing the
    two applies the geometric-series correction for a retry loop: exact for a
    single homogeneous loop, an approximation when a graph has several loops at
    different depths (each with its own escape dynamics) folded into one
    aggregate p_escape.

    Not currently called from anywhere in this repo.
    """
    def walk(state, visited):
        if state is None or state.type == 'event:end':
            return 0.0, 1.0
        if state.name in visited:
            return 0.0, 0.0
        visited = visited | {state.name}
        if state.type == 'event:intermediate:timer':
            own_delay = state.delay.mean()
        else:
            own_delay = 0.0
        delay_sum = 0.0
        escape = 0.0
        for t in state.transitions:
            d, e = walk(states.get(t.next_state), visited)
            delay_sum += t.probability * d
            escape += t.probability * e
        return own_delay + delay_sum, escape

    naive, p_escape = walk(start_state, frozenset())
    if p_escape <= 0:
        return naive
    return naive / p_escape

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
                parsed_runtime = isodate.parse_duration(runtime)
                # Duration.total_seconds() would silently return 0 for calendar-based
                # units (P1M, P1Y) — it only reflects the exact (day/hour/etc.) part,
                # since a month has no fixed length in seconds on its own. Resolving
                # against the actual start time instead gives the true elapsed time
                # (e.g. Feb correctly comes out shorter than Jan), and is a no-op for
                # plain timedeltas, so this works for every duration uniformly.
                start = global_clock.get_start_time()
                self.t = ((start + parsed_runtime) - start).total_seconds()
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
        recs_done = (
            self.total_recs is not None and self.record_count >= self.total_recs
        )
        time_done = (
            self.t is not None
            and (self.get_duration() > self.t or self.thread_end_event.is_set())
        )
        return recs_done or time_done

    def wait_for_end(self):
        """Generator: `yield from controller.wait_for_end()` blocks, within
        the simpy event loop, until this run's end condition is reached,
        polling is_done() once per simulated second via the given Clock.

        Not currently called from anywhere in this repo.
        """
        while not self.is_done():
            yield from self.global_clock.sleep(1.0)
        self.thread_end_event.set()

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
