#!/usr/bin/env python3
"""
tools/fmt_config.py — Canonical formatter for IEG preset config JSON files.

Run after generating or editing any config to enforce consistent field ordering
and compact/expanded forms. The formatter never loses data: it parses the
original JSON and the formatted output, compares them structurally, and aborts
with an error if they diverge.

Usage:
    python tools/fmt_config.py presets/configs/my_config.json
    python tools/fmt_config.py presets/configs/*.json
    python tools/fmt_config.py --check presets/configs/*.json   # CI: exit 1 if any file would change
"""

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Schema knowledge
# ---------------------------------------------------------------------------

STATE_TYPES = {
    'event:start:timer', 'event:start:message', 'event:intermediate:timer', 'event:end',
    'activity', 'gateway:exclusive',
    'subprocess', 'subprocess:multi:variables',
}

# Canonical field order for each state type.
# Any fields not listed here are appended at the end in their original order.
STATE_FIELD_ORDER = {
    'event:start:timer':        ['name', 'type', '_comment', 'cardinality_distribution', 'next'],
    'event:intermediate:timer': ['name', 'type', '_comment', 'cardinality_distribution', 'next'],
    'activity':                 ['name', 'type', '_comment', 'variables', 'emitter', 'next'],
    'gateway:exclusive':        ['name', 'type', '_comment', 'transitions'],
    'event:end':                ['name', 'type'],
    'subprocess':               ['name', 'type', '_comment', 'config', 'next'],
    'subprocess:multi:variables': ['name', 'type', '_comment', 'config', 'items', 'next'],
}

# Canonical field order for variable / dimension objects.
VAR_FIELD_ORDER = [
    'name', 'type', 'variable', 'template', 'value',
    'values', 'chars',
    'cardinality', 'length_distribution', 'distribution', 'cardinality_distribution',
    '_comment',
]

# Canonical field order for distribution objects.
DIST_FIELD_ORDER = [
    'type', 'mean', 'min', 'max', 'value', 'stddev',
    'components', 'weekly_pattern', 'daily_pattern', 'schedule',
]

INDENT = '  '

# Canonical dimension type ordering: clock first (always the record timestamp),
# then static/variable, then generators by complexity, then variable:template last.
# variable:template must sort after all generator types because templates are often
# used in variables blocks to compose values from previously-set generated variables
# (e.g. var_uri_path renders {{ var_category }}/{{ var_product }}). Sorting templates
# after generators ensures the referenced variables are set before the template runs.
_DIM_TYPE_RANK = {t: i for i, t in enumerate([
    'generator:clock',
    'static',
    'variable',
    'generator:enum',
    'generator:int',
    'generator:float',
    'generator:ipaddress',
    'generator:string',
    'generator:counter',
    'generator:timestamp',
    'generator:object',
    'generator:list',
    'variable:template',
])}


def _dim_sort_key(item):
    if not isinstance(item, dict):
        return (999, '')
    t = item.get('type', '')
    return (_DIM_TYPE_RANK.get(t, 500), item.get('name', ''))


# Distribution-valued keys that are always rendered on one line.
_ALWAYS_INLINE_KEYS = frozenset({'cardinality_distribution'})
# Distribution-valued keys that are inlined when they are simple (all-scalar).
_INLINE_IF_SIMPLE_KEYS = frozenset({'length_distribution'})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reorder(obj: dict, preferred: list) -> dict:
    """Return obj with keys in preferred order first, then remaining keys in original order."""
    result = {}
    for k in preferred:
        if k in obj:
            result[k] = obj[k]
    for k in obj:
        if k not in result:
            result[k] = obj[k]
    return result


def _is_state(obj) -> bool:
    return isinstance(obj, dict) and obj.get('type') in STATE_TYPES


def _is_variable_or_dimension(obj) -> bool:
    """Has name + type but is not a state."""
    return (
        isinstance(obj, dict)
        and 'name' in obj
        and 'type' in obj
        and obj.get('type') not in STATE_TYPES
    )


def _is_simple_distribution(obj) -> bool:
    """
    A distribution object eligible for single-line rendering:
    all-scalar values, no _comment, and ≤3 fields (type + at most 2 params).
    """
    return (
        isinstance(obj, dict)
        and 'type' in obj
        and 'name' not in obj
        and '_comment' not in obj
        and len(obj) <= 3
        and all(not isinstance(v, (dict, list)) for v in obj.values())
    )


def _is_transition(obj) -> bool:
    """A gateway transition: exactly next + probability."""
    return isinstance(obj, dict) and set(obj.keys()) <= {'next', 'probability'}


def _fits_one_line(obj, max_len: int = 80) -> bool:
    """True if the object serialises to a single JSON string within max_len chars."""
    return len(json.dumps(obj, ensure_ascii=False)) <= max_len


# ---------------------------------------------------------------------------
# Transform: reorder fields throughout the structure
# ---------------------------------------------------------------------------

def transform(obj):
    """Recursively reorder fields. Returns a new object; never drops data."""
    if isinstance(obj, list):
        transformed = [transform(item) for item in obj]
        # Sort arrays of variable/dimension objects by type rank, then name
        if transformed and all(_is_variable_or_dimension(item) for item in transformed):
            transformed = sorted(transformed, key=_dim_sort_key)
        return transformed
    if not isinstance(obj, dict):
        return obj

    if _is_state(obj):
        stype = obj.get('type', '')
        obj = _reorder(obj, STATE_FIELD_ORDER.get(stype, ['name', 'type', '_comment']))
    elif _is_variable_or_dimension(obj):
        obj = _reorder(obj, VAR_FIELD_ORDER)
    elif _is_simple_distribution(obj):
        obj = _reorder(obj, DIST_FIELD_ORDER)

    return {k: transform(v) for k, v in obj.items()}


# ---------------------------------------------------------------------------
# Format: render to a string with compact/expanded rules
# ---------------------------------------------------------------------------

def _inline(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def fmt(value, depth: int = 0, key: str = None) -> str:
    """Recursively render value as a formatted JSON string."""
    pad = INDENT * depth
    inner = INDENT * (depth + 1)

    if isinstance(value, list):
        if not value:
            return '[]'
        # All transitions → each on one line
        if all(_is_transition(item) for item in value):
            parts = [f'{inner}{_inline(item)}' for item in value]
            return '[\n' + ',\n'.join(parts) + '\n' + pad + ']'
        # values array → single line if fits, else pack multiple items per line
        if key == 'values':
            single = json.dumps(value, ensure_ascii=False)
            if len(single) <= 80:
                return single
            # Fill-pack: accumulate items onto a line until it would exceed 80 chars
            lines = []
            current = []
            for item in value:
                current.append(json.dumps(item, ensure_ascii=False))
                line_content = ', '.join(current)
                if len(inner) + len(line_content) > 80 and len(current) > 1:
                    current.pop()
                    lines.append(inner + ', '.join(current))
                    current = [json.dumps(item, ensure_ascii=False)]
            if current:
                lines.append(inner + ', '.join(current))
            return '[\n' + ',\n'.join(lines) + '\n' + pad + ']'
        # Normal list — one item per line
        parts = [f'{inner}{fmt(item, depth + 1)}' for item in value]
        return '[\n' + ',\n'.join(parts) + '\n' + pad + ']'

    if isinstance(value, dict):
        # event:end → single line
        if _is_state(value) and value.get('type') == 'event:end':
            return _inline(value)
        # Transition → single line
        if _is_transition(value):
            return _inline(value)
        # cardinality_distribution → always single line
        if key in _ALWAYS_INLINE_KEYS and _is_simple_distribution(value):
            return _inline(value)
        # delay / timer / length_distribution → single line if all-scalar
        if key in _INLINE_IF_SIMPLE_KEYS and _is_simple_distribution(value):
            return _inline(value)
        # variable/dimension objects → single line if they fit, else type+name open line
        if _is_variable_or_dimension(value):
            if value.get('type') in ('variable', 'variable:template', 'static', 'generator:clock') or _fits_one_line(value):
                return _inline(value)
            # name and type share the opening line; remaining fields expand below
            opening = (
                f'{inner}{json.dumps("name")}: {json.dumps(value["name"])}, '
                f'{json.dumps("type")}: {json.dumps(value["type"])}'
            )
            rest = [
                f'{inner}{json.dumps(k)}: {fmt(v, depth + 1, key=k)}'
                for k, v in value.items() if k not in ('name', 'type')
            ]
            return '{\n' + ',\n'.join([opening] + rest) + '\n' + pad + '}'
        # state objects → name and type share the opening line
        if _is_state(value) and 'name' in value:
            type_name = (
                f'{inner}{json.dumps("name")}: {json.dumps(value["name"])}, '
                f'{json.dumps("type")}: {json.dumps(value["type"])}'
            )
            rest = [
                f'{inner}{json.dumps(k)}: {fmt(v, depth + 1, key=k)}'
                for k, v in value.items() if k not in ('type', 'name')
            ]
            return '{\n' + ',\n'.join([type_name] + rest) + '\n' + pad + '}'
        # Empty object
        if not value:
            return '{}'
        # Default expanded
        parts = [
            f'{inner}{json.dumps(k)}: {fmt(v, depth + 1, key=k)}'
            for k, v in value.items()
        ]
        return '{\n' + ',\n'.join(parts) + '\n' + pad + '}'

    return json.dumps(value, ensure_ascii=False)


def format_config(config: dict) -> str:
    return fmt(transform(config)) + '\n'


# ---------------------------------------------------------------------------
# Safety check: structural equality after round-trip
# ---------------------------------------------------------------------------

def _assert_lossless(original_text: str, formatted_text: str, path: Path) -> None:
    """
    Parse both strings and compare as Python objects after applying the same
    transform (including sort) to the original. This catches dropped/mutated data
    while allowing intentional reorderings (e.g. dimension sort).
    Aborts with exit 2 if data was lost or mutated (indicates a formatter bug).
    """
    before = transform(json.loads(original_text))
    after = json.loads(formatted_text)
    if before != after:
        print(
            f'BUG: {path}: formatted output differs structurally from input.\n'
            'The formatter has a bug — original file left unchanged.',
            file=sys.stderr,
        )
        sys.exit(2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description='Format IEG preset config JSON files.')
    ap.add_argument('files', nargs='+', type=Path, metavar='FILE')
    ap.add_argument(
        '--check',
        action='store_true',
        help='Do not write files; exit 1 if any file would change (useful in CI).',
    )
    args = ap.parse_args()

    any_diff = False
    for path in args.files:
        raw = path.read_text(encoding='utf-8')

        try:
            config = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f'ERROR {path}: invalid JSON: {e}', file=sys.stderr)
            sys.exit(1)

        out = format_config(config)

        # Guarantee no data loss before touching the file
        _assert_lossless(raw, out, path)

        if out == raw:
            print(f'  ok  {path}')
        elif args.check:
            print(f' DIFF {path}')
            any_diff = True
        else:
            path.write_text(out, encoding='utf-8')
            print(f'  fmt {path}')

    if args.check and any_diff:
        sys.exit(1)


if __name__ == '__main__':
    main()
