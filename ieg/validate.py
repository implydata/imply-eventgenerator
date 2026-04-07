"""Pre-flight configuration validation for the event generator."""

import logging
import os
import re

from ieg.distributions import validate_distribution_desc
from ieg.dimensions import validate_dimension_desc
from ieg.states import State, Transition

logger = logging.getLogger('ieg')


def validate_config(config, template_name=None):
    """
    Validate a generator config dict.
    Logs errors and warnings directly and returns True (valid) or False (has fatal errors).
    Never raises — all problems are accumulated and reported before returning.
    Errors are fatal (generator cannot start). Warnings are non-fatal but likely mistakes.
    """
    valid = True

    # Top-level required fields
    if 'interarrival' not in config:
        logger.error("Config missing required field 'interarrival'")
        valid = False
    else:
        if not validate_distribution_desc(config['interarrival'], "interarrival"):
            valid = False

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
        # Collect state names first (needed for cross-cutting checks)
        for state in config['states']:
            if 'name' in state:
                state_names.add(state['name'])

        # Collect all variable names set by any state
        all_set_variables = set()
        for state in config['states']:
            for var in state.get('variables', []):
                if 'name' in var:
                    all_set_variables.add(var['name'])
            for var in state.get('variables_on_entry', []):
                if 'name' in var:
                    all_set_variables.add(var['name'])

        # Per-state validation
        for i, state in enumerate(config['states']):
            ctx = f"state '{state.get('name', f'[{i}]')}'"
            if not State.validate_desc(state, emitter_names, ctx):
                valid = False
            if 'delay' in state:
                if not validate_distribution_desc(state['delay'], f"{ctx} delay"):
                    valid = False
            for var in state.get('variables', []):
                vctx = f"{ctx}, variable '{var.get('name', '?')}'"
                if var.get('type', '').lower() == 'variable':
                    logger.error("%s: type 'variable' is not valid in a state's 'variables' block — it can only be used in emitter dimensions", vctx)
                    valid = False
                elif not validate_dimension_desc(var, vctx):
                    valid = False
            for var in state.get('variables_on_entry', []):
                vctx = f"{ctx}, variables_on_entry '{var.get('name', '?')}'"
                if var.get('type', '').lower() == 'variable':
                    logger.error("%s: type 'variable' is not valid in a state's 'variables_on_entry' block — it can only be used in emitter dimensions", vctx)
                    valid = False
                elif not validate_dimension_desc(var, vctx):
                    valid = False

        # Cross-cutting: transition destination existence
        for state in config['states']:
            sname = state.get('name', '?')
            for trans in state.get('transitions', []):
                nxt = trans.get('next', '')
                if nxt.lower() != 'stop' and nxt not in state_names:
                    logger.error("state '%s': transition to undefined state '%s'", sname, nxt)
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

        # Cross-cutting: infinite loop detection via reachability to 'stop'
        # A state can escape if it has any path (direct or indirect) to 'stop'
        can_escape = set()
        for state in config['states']:
            for trans in state.get('transitions', []):
                if trans.get('next', '').lower() == 'stop':
                    can_escape.add(state.get('name', ''))
                    break
        changed = True
        while changed:
            changed = False
            for state in config['states']:
                sname = state.get('name', '')
                if sname not in can_escape:
                    for trans in state.get('transitions', []):
                        if trans.get('next', '') in can_escape:
                            can_escape.add(sname)
                            changed = True
                            break

        # Find states reachable from the initial state (first state in list)
        if config['states']:
            reachable = set()
            frontier = {config['states'][0].get('name', '')}
            while frontier:
                sname = frontier.pop()
                if sname in reachable:
                    continue
                reachable.add(sname)
                state = next((s for s in config['states'] if s.get('name') == sname), None)
                if state:
                    for trans in state.get('transitions', []):
                        nxt = trans.get('next', '')
                        if nxt.lower() != 'stop' and nxt in state_names:
                            frontier.add(nxt)

            for sname in sorted(reachable - can_escape):
                logger.warning("state '%s': no path to 'stop' — potential infinite loop", sname)
                # do NOT set valid = False — code runs fine, just never terminates
            for sname in sorted(state_names - reachable):
                logger.warning("state '%s': unreachable from the initial state", sname)

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
