"""Pre-flight configuration validation for the event generator."""

from ieg.distributions import validate_distribution_desc
from ieg.dimensions import validate_dimension_desc
from ieg.states import State, Transition


def validate_config(config):
    """
    Validate a generator config dict.
    Returns (errors, warnings) — both lists of strings.
    Never raises — all problems are accumulated and returned.
    Errors are fatal (generator cannot start). Warnings are non-fatal but likely mistakes.
    """
    errors = []
    warnings = []

    # Top-level required fields
    if 'interarrival' not in config:
        errors.append("missing required field 'interarrival'")
    else:
        errors += validate_distribution_desc(config['interarrival'], "interarrival")

    # Emitters
    emitter_names = set()
    if 'emitters' not in config:
        errors.append("missing required field 'emitters'")
    elif not isinstance(config['emitters'], list) or len(config['emitters']) == 0:
        errors.append("'emitters' must be a non-empty list")
    else:
        for i, emitter in enumerate(config['emitters']):
            ctx = f"emitter '{emitter.get('name', f'[{i}]')}'"
            if 'name' not in emitter:
                errors.append(f"{ctx}: missing required field 'name'")
            else:
                emitter_names.add(emitter['name'])
            if 'dimensions' not in emitter:
                errors.append(f"{ctx}: missing required field 'dimensions'")
            else:
                for dim in emitter.get('dimensions', []):
                    e, w = validate_dimension_desc(dim, f"{ctx}, dimension '{dim.get('name', '?')}'")
                    errors += e
                    warnings += w

    # States
    state_names = set()
    if 'states' not in config:
        errors.append("missing required field 'states'")
    elif not isinstance(config['states'], list) or len(config['states']) == 0:
        errors.append("'states' must be a non-empty list")
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
            e, w = State.validate_desc(state, emitter_names, ctx)
            errors += e
            warnings += w
            if 'delay' in state:
                errors += validate_distribution_desc(state['delay'], f"{ctx} delay")
            for var in state.get('variables', []):
                e, w = validate_dimension_desc(var, f"{ctx}, variable '{var.get('name', '?')}'")
                errors += e
                warnings += w
            for var in state.get('variables_on_entry', []):
                e, w = validate_dimension_desc(var, f"{ctx}, variables_on_entry '{var.get('name', '?')}'")
                errors += e
                warnings += w

        # Cross-cutting: transition destination existence
        for state in config['states']:
            sname = state.get('name', '?')
            for trans in state.get('transitions', []):
                nxt = trans.get('next', '')
                if nxt.lower() != 'stop' and nxt not in state_names:
                    errors.append(f"state '{sname}': transition to undefined state '{nxt}'")

        # Cross-cutting: variable references in emitter dimensions
        for emitter in config.get('emitters', []):
            ename = emitter.get('name', '?')
            for dim in emitter.get('dimensions', []):
                if dim.get('type', '').lower() == 'variable':
                    ref = dim.get('variable', '')
                    if ref and ref not in all_set_variables:
                        errors.append(
                            f"emitter '{ename}', dimension '{dim.get('name', '?')}':"
                            f" references variable '{ref}' which is never set by any state"
                        )

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
                errors.append(f"state '{sname}': no path to 'stop' — potential infinite loop")
            for sname in sorted(state_names - reachable):
                warnings.append(f"state '{sname}': unreachable from the initial state")

    return errors, warnings
