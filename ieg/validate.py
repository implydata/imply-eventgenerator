"""Pre-flight configuration validation for the event generator."""

import logging
import os
import re

from ieg.distributions import validate_distribution_desc
from ieg.dimensions import validate_dimension_desc

logger = logging.getLogger('ieg')

_VALID_STATE_TYPES = {'activity', 'gateway:exclusive', 'event:start:timer', 'event:start:message',
                      'event:intermediate:timer', 'event:end', 'subprocess:multi:variables'}


def _validate_state_desc(desc, emitter_names, context):
    """Validate a state config dict. Logs errors and returns bool."""
    valid = True
    if 'name' not in desc:
        logger.error("%s: missing required field 'name'", context)
        valid = False

    state_type = desc.get('type')
    if state_type is None:
        logger.error("%s: missing required field 'type'", context)
        return False
    if state_type not in _VALID_STATE_TYPES:
        logger.error("%s: unknown state type '%s'", context, state_type)
        return False

    if state_type == 'event:end':
        if desc.get('emitter') is not None:
            logger.error("%s: event:end must not have an emitter", context)
            valid = False
        if 'variables' in desc or 'variables_on_entry' in desc:
            logger.error("%s: event:end must not have variables — only activities can set variables", context)
            valid = False
        return valid

    if state_type == 'event:start:timer':
        if 'cardinality_distribution' not in desc:
            logger.error("%s: event:start:timer missing required field 'cardinality_distribution'", context)
            valid = False
        if desc.get('emitter') is not None:
            logger.error("%s: event:start:timer must not have an emitter", context)
            valid = False
        if 'next' not in desc:
            logger.error("%s: event:start:timer missing required field 'next'", context)
            valid = False
        elif not isinstance(desc['next'], str):
            logger.error("%s: event:start:timer 'next' must be a string", context)
            valid = False
        if 'transitions' in desc:
            logger.error("%s: event:start:timer uses 'next', not 'transitions'", context)
            valid = False
        if 'variables' in desc or 'variables_on_entry' in desc:
            logger.error("%s: event:start:timer must not have variables — only activities can set variables", context)
            valid = False
        return valid

    if state_type == 'event:start:message':
        if 'cardinality_distribution' in desc:
            logger.error("%s: event:start:message must not have 'cardinality_distribution' — it is triggered by the parent, not a timer", context)
            valid = False
        if desc.get('emitter') is not None:
            logger.error("%s: event:start:message must not have an emitter", context)
            valid = False
        if 'next' not in desc:
            logger.error("%s: event:start:message missing required field 'next'", context)
            valid = False
        elif not isinstance(desc['next'], str):
            logger.error("%s: event:start:message 'next' must be a string", context)
            valid = False
        if 'transitions' in desc:
            logger.error("%s: event:start:message uses 'next', not 'transitions'", context)
            valid = False
        return valid

    if state_type == 'event:intermediate:timer':
        if 'cardinality_distribution' not in desc:
            logger.error("%s: event:intermediate:timer missing required field 'cardinality_distribution'", context)
            valid = False
        if 'next' not in desc:
            logger.error("%s: event:intermediate:timer missing required field 'next'", context)
            valid = False
        elif not isinstance(desc['next'], str):
            logger.error("%s: event:intermediate:timer 'next' must be a string", context)
            valid = False
        if desc.get('emitter') is not None:
            logger.error("%s: event:intermediate:timer must not have an emitter", context)
            valid = False
        if 'transitions' in desc:
            logger.error("%s: event:intermediate:timer uses 'next', not 'transitions'", context)
            valid = False
        if 'variables' in desc or 'variables_on_entry' in desc:
            logger.error("%s: event:intermediate:timer must not have variables — only activities can set variables", context)
            valid = False
        return valid

    if state_type == 'activity':
        if 'cardinality_distribution' in desc:
            logger.error("%s: activity must not have 'cardinality_distribution' — precede it with event:intermediate:timer", context)
            valid = False
        if 'transitions' in desc:
            logger.error("%s: activity uses 'next', not 'transitions' — add a gateway:exclusive for routing", context)
            valid = False
        if 'next' not in desc:
            logger.error("%s: activity missing required field 'next'", context)
            valid = False
        elif not isinstance(desc['next'], str):
            logger.error("%s: activity 'next' must be a string", context)
            valid = False
        if 'variables_on_entry' in desc:
            logger.error("%s: 'variables_on_entry' is not supported — use 'variables' in an activity", context)
            valid = False
        emitter = desc.get('emitter')
        if emitter is not None and emitter not in emitter_names:
            logger.error("%s: references emitter '%s' which is not defined in 'emitters'", context, emitter)
            valid = False
        return valid

    if state_type == 'gateway:exclusive':
        if desc.get('emitter') is not None:
            logger.error("%s: gateway:exclusive must not have an emitter", context)
            valid = False
        if 'cardinality_distribution' in desc:
            logger.error("%s: gateway:exclusive must not have 'cardinality_distribution'", context)
            valid = False
        if 'next' in desc:
            logger.error("%s: gateway:exclusive uses 'transitions', not 'next'", context)
            valid = False
        if 'variables' in desc or 'variables_on_entry' in desc:
            logger.error("%s: gateway:exclusive must not have variables — only activities can set variables", context)
            valid = False
        transitions = desc.get('transitions')
        if not transitions or not isinstance(transitions, list):
            logger.error("%s: gateway:exclusive missing required field 'transitions'", context)
            valid = False
        else:
            total_prob = 0.0
            for i, trans in enumerate(transitions):
                tctx = f"{context}, transition [{i}]"
                if 'next' not in trans:
                    logger.error("%s: missing required field 'next'", tctx)
                    valid = False
                elif not isinstance(trans['next'], str):
                    logger.error("%s: 'next' must be a string, got %s", tctx, type(trans['next']).__name__)
                    valid = False
                if 'probability' not in trans:
                    logger.error("%s: missing required field 'probability'", tctx)
                    valid = False
                else:
                    try:
                        p = float(trans['probability'])
                        if not (0 < p <= 1):
                            logger.error("%s: 'probability' must be in (0, 1], got %s", tctx, trans['probability'])
                            valid = False
                        total_prob += p
                    except (TypeError, ValueError):
                        logger.error("%s: 'probability' must be a number, got %r", tctx, trans['probability'])
                        valid = False
            if abs(total_prob - 1.0) > 0.01:
                logger.error("%s: transition probabilities sum to %.4f, not 1.0", context, total_prob)
                valid = False
        return valid

    if state_type == 'subprocess:multi:variables':
        if 'items' not in desc:
            logger.error("%s: subprocess:multi:variables missing required field 'items'", context)
            valid = False
        else:
            in_val = desc['items']
            if not isinstance(in_val, list) or len(in_val) == 0:
                logger.error("%s: subprocess:multi:variables 'in' must be a non-empty list", context)
                valid = False
            else:
                for i, item in enumerate(in_val):
                    if not isinstance(item, list) or len(item) == 0:
                        logger.error("%s: subprocess:multi:variables 'in[%d]' must be a non-empty list of variable specs", context, i)
                        valid = False
        if 'states' not in desc:
            logger.error("%s: subprocess:multi:variables missing required field 'states'", context)
            valid = False
        elif not isinstance(desc['states'], str):
            logger.error("%s: subprocess:multi:variables 'states' must be a string (file path)", context)
            valid = False
        if 'next' not in desc:
            logger.error("%s: subprocess:multi:variables missing required field 'next'", context)
            valid = False
        elif not isinstance(desc['next'], str):
            logger.error("%s: subprocess:multi:variables 'next' must be a string", context)
            valid = False
        if desc.get('emitter') is not None:
            logger.error("%s: subprocess:multi:variables must not have an emitter", context)
            valid = False
        if 'variables' in desc:
            logger.error("%s: subprocess:multi:variables must not have variables", context)
            valid = False
        if 'transitions' in desc:
            logger.error("%s: subprocess:multi:variables uses 'next', not 'transitions'", context)
            valid = False
        return valid

    return valid


def validate_config(config, template_name=None):
    """
    Validate a generator config dict.
    Logs errors and warnings directly and returns True (valid) or False (has fatal errors).
    Never raises — all problems are accumulated and reported before returning.
    Errors are fatal (generator cannot start). Warnings are non-fatal but likely mistakes.
    """
    valid = True

    # Emitters
    emitter_names = set()
    if 'emitters' not in config:
        logger.error("Config missing required field 'emitters'")
        valid = False
    elif not isinstance(config['emitters'], list) or len(config['emitters']) == 0:
        logger.error("Config 'emitters' must be a non-empty list")
        valid = False
    else:
        for i, emitter in enumerate(config['emitters']):
            ctx = f"emitter '{emitter.get('name', f'[{i}]')}'"
            if 'name' not in emitter:
                logger.error("%s: missing required field 'name'", ctx)
                valid = False
            else:
                emitter_names.add(emitter['name'])
            if 'dimensions' not in emitter:
                logger.error("%s: missing required field 'dimensions'", ctx)
                valid = False
            else:
                for dim in emitter.get('dimensions', []):
                    if not validate_dimension_desc(dim, f"{ctx}, dimension '{dim.get('name', '?')}'"):
                        valid = False

    # States
    state_names = set()
    if 'states' not in config:
        logger.error("Config missing required field 'states'")
        valid = False
    elif not isinstance(config['states'], list) or len(config['states']) == 0:
        logger.error("Config 'states' must be a non-empty list")
        valid = False
    else:
        # Collect state names and types first (needed for cross-cutting checks)
        for state in config['states']:
            if 'name' in state:
                state_names.add(state['name'])

        end_state_names = {s['name'] for s in config['states'] if s.get('type') == 'event:end' and 'name' in s}

        # Cross-cutting: exactly one event:start:timer
        start_states = [s for s in config['states'] if s.get('type') == 'event:start:timer']
        if len(start_states) == 0:
            logger.error("Config has no event:start:timer state")
            valid = False
        elif len(start_states) > 1:
            logger.error("Config has multiple event:start:timer states — only one is allowed")
            valid = False
        else:
            timer_desc = start_states[0].get('cardinality_distribution')
            if timer_desc and not validate_distribution_desc(timer_desc, "event:start:timer.cardinality_distribution"):
                valid = False

        # Cross-cutting: at least one event:end
        if not end_state_names:
            logger.error("Config has no event:end state")
            valid = False

        # Collect all variable names set by any state (activities only)
        all_set_variables = set()
        for state in config['states']:
            for var in state.get('variables', []):
                if 'name' in var:
                    all_set_variables.add(var['name'])

        # Per-state validation
        for i, state in enumerate(config['states']):
            ctx = f"state '{state.get('name', f'[{i}]')}'"
            if not _validate_state_desc(state, emitter_names, ctx):
                valid = False
            state_type = state.get('type')
            if state_type == 'event:intermediate:timer' and 'cardinality_distribution' in state:
                if not validate_distribution_desc(state['cardinality_distribution'], f"{ctx} cardinality_distribution"):
                    valid = False
            if state_type == 'event:start:timer' and 'cardinality_distribution' in state:
                if not validate_distribution_desc(state['cardinality_distribution'], f"{ctx} cardinality_distribution"):
                    valid = False
            for var in state.get('variables', []):
                vctx = f"{ctx}, variable '{var.get('name', '?')}'"
                if var.get('type', '').lower() == 'variable':
                    logger.error("%s: type 'variable' is not valid in a state's 'variables' block — it can only be used in emitter dimensions", vctx)
                    valid = False
                elif not validate_dimension_desc(var, vctx):
                    valid = False

        # Cross-cutting: transition destination existence
        for state in config['states']:
            sname = state.get('name', '?')
            for trans in state.get('transitions', []):
                nxt = trans.get('next', '')
                if nxt not in state_names:
                    logger.error("state '%s': transition to undefined state '%s'", sname, nxt)
                    valid = False
            if 'next' in state:
                nxt = state['next']
                if nxt not in state_names:
                    logger.error("state '%s': 'next' points to undefined state '%s'", sname, nxt)
                    valid = False

        # Cross-cutting: variable references in emitter dimensions
        for emitter in config.get('emitters', []):
            ename = emitter.get('name', '?')
            for dim in emitter.get('dimensions', []):
                if dim.get('type', '').lower() == 'variable':
                    ref = dim.get('variable', '')
                    if ref and ref not in all_set_variables:
                        logger.error(
                            "emitter '%s', dimension '%s': references variable '%s' which is never set by any state",
                            ename, dim.get('name', '?'), ref
                        )
                        valid = False

        def outgoing(state):
            """All next-state names from a state, regardless of how they're expressed."""
            nxts = [t.get('next', '') for t in state.get('transitions', [])]
            if 'next' in state:  # activity, event:start:timer, event:intermediate:timer
                nxts.append(state['next'])
            return [n for n in nxts if n in state_names]

        # Cross-cutting: infinite loop detection — can a state reach an event:end?
        can_escape = set(end_state_names)
        for state in config['states']:
            if any(n in end_state_names for n in outgoing(state)):
                can_escape.add(state.get('name', ''))
        changed = True
        while changed:
            changed = False
            for state in config['states']:
                sname = state.get('name', '')
                if sname not in can_escape:
                    if any(n in can_escape for n in outgoing(state)):
                        can_escape.add(sname)
                        changed = True

        # Find states reachable from event:start:timer
        if start_states:
            reachable = set()
            frontier = {start_states[0].get('name', '')}
            while frontier:
                sname = frontier.pop()
                if sname in reachable:
                    continue
                reachable.add(sname)
                state = next((s for s in config['states'] if s.get('name') == sname), None)
                if state:
                    for nxt in outgoing(state):
                        frontier.add(nxt)

            for sname in sorted(reachable - can_escape):
                logger.warning("state '%s': no path to event:end — potential infinite loop", sname)
            for sname in sorted(state_names - reachable):
                logger.warning("state '%s': unreachable from event:start:timer", sname)

    # Templates block validation
    templates = config.get('templates', {})
    if template_name is not None:
        if not templates:
            logger.error("--template '%s' specified but config has no 'templates' block", template_name)
            valid = False
        elif template_name not in templates:
            available = ', '.join(templates.keys())
            logger.error("Template '%s' not found in config. Available: %s", template_name, available)
            valid = False
        else:
            body = templates[template_name].get('body', '')
            unresolved = [v for v in re.findall(r"env\.(\w+)", body)
                          if v != 'get' and v not in os.environ]
            for var in unresolved:
                logger.error("Template '%s': environment variable '%s' is not set", template_name, var)
            if unresolved:
                valid = False

    return valid
