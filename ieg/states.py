"""State machine classes: one class per state type, plus Controller.

Each StateBase subclass models one state type in the Actor lifecycle graph.
Controller tracks simulation end conditions (record count or elapsed duration).

See docs/states.md for the config-level reference.
"""

import itertools
import logging
import random
import threading

import isodate

from ieg.dimensions import get_variables
from ieg.distributions import parse_distribution

logger = logging.getLogger("ieg")


class StateBase:
    """Base class for one node in the Actor lifecycle state machine.

    Each subclass handles one state type. parse() builds an instance from a
    config dict, validate_desc() checks a config dict without building one,
    run() performs the state's side effects inside a simpy process, and
    next_state() picks the name of the state to move to.
    """

    type = None

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"{type(self).__name__}(name={self.name})"

    @classmethod
    def parse(cls, desc, emitters, clock):
        """Build an instance from a state config dict.

        Args:
            desc: The state's config dict.
            emitters: Map of emitter name to its parsed dimensions.
            clock: The simulation Clock, for distributions and dimensions that need it.

        Returns:
            An instance of the subclass.
        """
        raise NotImplementedError

    @staticmethod
    def validate_desc(desc, emitter_names, context):
        """Validate a state config dict of this type. Logs errors and returns bool."""
        raise NotImplementedError

    def run(self, driver, variables):
        """Generator: perform this state's side effects.

        Run with `yield from state.run(driver, variables)` inside a simpy
        process. Only timer states actually yield.

        Args:
            driver: The DataDriver running the session.
            variables: The session's worker variables, updated in place.
        """
        return
        yield

    def next_state(self):
        """Return the name of the next state, or None to end the session."""
        raise NotImplementedError


class _SingleNextState(StateBase):
    """A state with exactly one successor, named by its 'next' field."""

    def __init__(self, name, next_name):
        super().__init__(name)
        self.next_name = next_name

    def next_state(self):
        # Draw and discard one random number, matching the single-option
        # random.choices() call that routing used to make for every state.
        random.random()
        return self.next_name


def _no_variables(desc, state_type, context):
    if "variables" in desc or "variables_on_entry" in desc:
        logger.error(
            "%s: %s must not have variables — only activities can set variables",
            context,
            state_type,
        )
        return False
    return True


def _next_is_string(desc, state_type, context):
    if "next" not in desc:
        logger.error("%s: %s missing required field 'next'", context, state_type)
        return False
    if not isinstance(desc["next"], str):
        logger.error("%s: %s 'next' must be a string", context, state_type)
        return False
    return True


class EventStartTimerState(_SingleNextState):
    """The session's entry point. Its cardinality_distribution sets how often
    sessions start; DataDriver.arrival_process reads it, not the state itself."""

    type = "event:start:timer"

    @classmethod
    def parse(cls, desc, emitters, clock):
        return cls(desc["name"], desc["next"])

    @staticmethod
    def validate_desc(desc, emitter_names, context):
        valid = True
        t = "event:start:timer"
        if "cardinality_distribution" not in desc:
            logger.error(
                "%s: %s missing required field 'cardinality_distribution'", context, t
            )
            valid = False
        if desc.get("emitter") is not None:
            logger.error("%s: %s must not have an emitter", context, t)
            valid = False
        if not _next_is_string(desc, t, context):
            valid = False
        if "transitions" in desc:
            logger.error("%s: %s uses 'next', not 'transitions'", context, t)
            valid = False
        if not _no_variables(desc, t, context):
            valid = False
        return valid


class EventIntermediateTimerState(_SingleNextState):
    """Advances the session's clock by a sampled delay, without emitting."""

    type = "event:intermediate:timer"

    def __init__(self, name, next_name, delay):
        super().__init__(name, next_name)
        self.delay = delay

    @classmethod
    def parse(cls, desc, emitters, clock):
        delay = parse_distribution(desc["cardinality_distribution"], clock=clock)
        return cls(desc["name"], desc["next"], delay)

    @staticmethod
    def validate_desc(desc, emitter_names, context):
        valid = True
        t = "event:intermediate:timer"
        if "cardinality_distribution" not in desc:
            logger.error(
                "%s: %s missing required field 'cardinality_distribution'", context, t
            )
            valid = False
        if not _next_is_string(desc, t, context):
            valid = False
        if desc.get("emitter") is not None:
            logger.error("%s: %s must not have an emitter", context, t)
            valid = False
        if "transitions" in desc:
            logger.error("%s: %s uses 'next', not 'transitions'", context, t)
            valid = False
        if not _no_variables(desc, t, context):
            valid = False
        return valid

    def run(self, driver, variables):
        yield from driver.global_clock.sleep(float(self.delay.get_sample()))


class ActivityState(_SingleNextState):
    """Sets variables, then emits a record if the state names an emitter."""

    type = "activity"

    def __init__(self, name, next_name, variables, dimensions):
        super().__init__(name, next_name)
        self.variables = variables
        self.dimensions = dimensions

    @classmethod
    def parse(cls, desc, emitters, clock):
        emitter_name = desc.get("emitter")
        dimensions = emitters[emitter_name] if emitter_name is not None else None
        variables = get_variables(desc.get("variables", []), clock)
        return cls(desc["name"], desc["next"], variables, dimensions)

    @staticmethod
    def validate_desc(desc, emitter_names, context):
        valid = True
        if "cardinality_distribution" in desc:
            logger.error(
                "%s: activity must not have 'cardinality_distribution' — "
                "precede it with event:intermediate:timer",
                context,
            )
            valid = False
        if "transitions" in desc:
            logger.error(
                "%s: activity uses 'next', not 'transitions' — add a "
                "gateway:exclusive for routing",
                context,
            )
            valid = False
        if not _next_is_string(desc, "activity", context):
            valid = False
        if "variables_on_entry" in desc:
            logger.error(
                "%s: 'variables_on_entry' is not supported — use "
                "'variables' in an activity",
                context,
            )
            valid = False
        emitter = desc.get("emitter")
        if emitter is not None and emitter not in emitter_names:
            logger.error(
                "%s: references emitter '%s' which is not defined in 'emitters'",
                context,
                emitter,
            )
            valid = False
        return valid

    def run(self, driver, variables):
        driver.set_variable_values(variables, self.variables)
        if self.dimensions is not None:
            record = driver.create_record(self.dimensions, variables)
            driver._emit(driver.render_record(record), driver.global_clock.now())
            driver.sim_control.inc_rec_count()
        return
        yield


class GatewayExclusiveState(StateBase):
    """Routes to one of several next states, chosen by weighted probability."""

    type = "gateway:exclusive"

    def __init__(self, name, next_names, probabilities):
        super().__init__(name)
        self.next_names = next_names
        # random.choices(weights=...) recomputes this cumulative sum on every
        # call; the probabilities never change, so compute it once.
        self._cum_weights = list(itertools.accumulate(probabilities))

    @classmethod
    def parse(cls, desc, emitters, clock):
        transitions = desc["transitions"]
        return cls(
            desc["name"],
            [t["next"] for t in transitions],
            [float(t["probability"]) for t in transitions],
        )

    @staticmethod
    def validate_desc(desc, emitter_names, context):
        valid = True
        t = "gateway:exclusive"
        if desc.get("emitter") is not None:
            logger.error("%s: %s must not have an emitter", context, t)
            valid = False
        if "cardinality_distribution" in desc:
            logger.error("%s: %s must not have 'cardinality_distribution'", context, t)
            valid = False
        if "next" in desc:
            logger.error("%s: %s uses 'transitions', not 'next'", context, t)
            valid = False
        if not _no_variables(desc, t, context):
            valid = False
        transitions = desc.get("transitions")
        if not transitions or not isinstance(transitions, list):
            logger.error("%s: %s missing required field 'transitions'", context, t)
            return False
        total_prob = 0.0
        for i, trans in enumerate(transitions):
            if not _validate_transition(trans, f"{context}, transition [{i}]"):
                valid = False
            try:
                total_prob += float(trans.get("probability", 0))
            except (TypeError, ValueError):
                pass
        if abs(total_prob - 1.0) > 0.01:
            logger.error(
                "%s: transition probabilities sum to %.4f, not 1.0", context, total_prob
            )
            valid = False
        return valid

    def next_state(self):
        return random.choices(self.next_names, cum_weights=self._cum_weights, k=1)[0]


def _validate_transition(desc, context):
    """Validate one entry in a gateway's transitions list. Logs errors and returns bool."""
    valid = True
    if "next" not in desc:
        logger.error("%s: transition missing required field 'next'", context)
        valid = False
    elif not isinstance(desc["next"], str):
        logger.error(
            "%s: transition 'next' must be a string, got %s",
            context,
            type(desc["next"]).__name__,
        )
        valid = False
    if "probability" not in desc:
        logger.error("%s: transition missing required field 'probability'", context)
        valid = False
    else:
        try:
            p = float(desc["probability"])
            if not (0 < p <= 1):
                logger.error(
                    "%s: transition 'probability' must be in (0, 1], got %s",
                    context,
                    desc["probability"],
                )
                valid = False
        except (TypeError, ValueError):
            logger.error(
                "%s: transition 'probability' must be a number, got %r",
                context,
                desc["probability"],
            )
            valid = False
    return valid


class EventEndState(StateBase):
    """Ends the session. Sessions stop on reaching it, so it never runs."""

    type = "event:end"

    @classmethod
    def parse(cls, desc, emitters, clock):
        return cls(desc["name"])

    @staticmethod
    def validate_desc(desc, emitter_names, context):
        valid = True
        if desc.get("emitter") is not None:
            logger.error("%s: event:end must not have an emitter", context)
            valid = False
        if not _no_variables(desc, "event:end", context):
            valid = False
        return valid

    def next_state(self):
        return None


STATE_CLASSES = {
    cls.type: cls
    for cls in (
        EventStartTimerState,
        EventIntermediateTimerState,
        ActivityState,
        GatewayExclusiveState,
        EventEndState,
    )
}


def validate_state_desc(desc, emitter_names, context):
    """Validate one state config dict. Logs errors and returns bool.

    Args:
        desc: The state's config dict.
        emitter_names: Names of the emitters the config defines.
        context: Prefix for log messages, such as "state 'setup'".

    Returns:
        True if the state is valid.
    """
    valid = True
    if "name" not in desc:
        logger.error("%s: missing required field 'name'", context)
        valid = False
    state_type = desc.get("type")
    if state_type is None:
        logger.error("%s: missing required field 'type'", context)
        return False
    cls = STATE_CLASSES.get(state_type)
    if cls is None:
        logger.error("%s: unknown state type '%s'", context, state_type)
        return False
    return cls.validate_desc(desc, emitter_names, context) and valid


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
        recs_done = self.total_recs is not None and self.record_count >= self.total_recs
        time_done = self.t is not None and (
            self.get_duration() > self.t or self.thread_end_event.is_set()
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
