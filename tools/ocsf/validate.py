#!/usr/bin/env python3
"""
tools/ocsf/validate.py — Validate generator output against the real OCSF JSON Schema.

Runs a config through generator.py with a given --template, then checks every
emitted record against the actual OCSF class schema (built locally by the
ocsf-json-schema package — no network calls, works offline once installed).
The OCSF class is read from each record's own class_name field, so there's no
--class flag to get wrong.

Usage:
    python tools/ocsf/validate.py -c presets/configs/vpc_flow_logs.json --template ocsf:network_activity
    python tools/ocsf/validate.py -c presets/configs/ssh_auth.json --template ocsf:authentication -n 2000
    python tools/ocsf/validate.py -c presets/configs/ecommerce.json --template ocsf:http_activity -r PT12H

Exits 0 if every record validates, 1 otherwise — safe to wire into CI or a
pre-commit hook alongside tools/fmt_config.py --check.

See tools/ocsf/README.md for the field-mapping conventions used across the
existing ocsf:* templates (activity_id/severity_id derivation, etc.).
"""

import argparse
import json
import subprocess
import sys

from jsonschema import Draft202012Validator
from ocsf_json_schema import OcsfJsonSchemaEmbedded, get_ocsf_schema
from rich.console import Console

err = Console(stderr=True)

DEFAULT_START = "2025-01-01T00:00:00"
DEFAULT_DURATION = "PT6H"
DEFAULT_SEED = 42
DEFAULT_VERSION = "1.4.0"
DEFAULT_SHOW_FAILURES = 5


def build_generator_cmd(config, template, start, seed, n, duration):
    cmd = [
        sys.executable, "generator.py",
        "-c", config,
        "--template", template,
        "-s", start,
        f"--seed={seed}",
    ]
    cmd += ["-n", str(n)] if n else ["-r", duration]
    return cmd


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-c", "--config", required=True, help="Generator config JSON")
    parser.add_argument("--template", required=True,
                         help="Template name to validate (e.g. ocsf:network_activity)")
    parser.add_argument("-s", "--start", default=DEFAULT_START,
                         help=f"Synthetic clock start (default: {DEFAULT_START})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--version", default=DEFAULT_VERSION,
                         help=f"OCSF schema version (default: {DEFAULT_VERSION})")
    parser.add_argument("--show-failures", type=int, default=DEFAULT_SHOW_FAILURES,
                         help="Number of distinct failures to print (default: %(default)s)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-n", type=int, default=None, help="Number of records to generate")
    group.add_argument("-r", "--duration", default=None,
                        help=f"Simulated duration, e.g. PT6H (default: {DEFAULT_DURATION})")
    args = parser.parse_args()
    duration = args.duration or DEFAULT_DURATION

    cmd = build_generator_cmd(args.config, args.template, args.start, args.seed, args.n, duration)
    err.print(f"[dim]$ {' '.join(cmd)}[/dim]")

    ocsf_schema = OcsfJsonSchemaEmbedded(get_ocsf_schema(version=args.version))
    validators = {}

    def validator_for(class_uid):
        if class_uid not in validators:
            class_name = ocsf_schema.schema.lookup_class_name_from_uid(class_uid)
            schema = ocsf_schema.get_class_schema(class_name=class_name)
            validators[class_uid] = Draft202012Validator(schema)
        return validators[class_uid]

    total = 0
    passed = 0
    # (class_uid, message, path) -> [count, example]
    failures_by_key = {}

    def record_failure(class_uid, message, path, example):
        key = (class_uid, message, tuple(path))
        if key not in failures_by_key:
            failures_by_key[key] = [0, example]
        failures_by_key[key][0] += 1

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            record_failure(None, f"invalid JSON: {e}", [], line)
            continue

        class_uid = event.get("class_uid")
        if class_uid is None:
            record_failure(None, "record has no class_uid field — cannot select an OCSF schema", [], event)
            continue

        try:
            errors = list(validator_for(class_uid).iter_errors(event))
        except Exception as e:
            record_failure(class_uid, f"could not load schema for class_uid {class_uid}: {e}", [], event)
            continue

        if errors:
            e = errors[0]
            record_failure(class_uid, e.message, e.path, event)
        else:
            passed += 1

    stderr_output = proc.stderr.read()
    proc.wait()
    if proc.returncode != 0:
        err.print(f"[red]generator.py exited {proc.returncode}[/red]\n{stderr_output}")
        sys.exit(1)

    failed = total - passed
    color = "green" if failed == 0 else "red"
    err.print(f"[{color}]total={total} passed={passed} failed={failed}[/{color}]")

    if failures_by_key:
        err.print(f"\n[red]--- distinct failures (showing up to {args.show_failures}) ---[/red]")
        ranked = sorted(failures_by_key.items(), key=lambda kv: -kv[1][0])
        for (class_uid, message, path), (count, example) in ranked[: args.show_failures]:
            err.print(f"  x{count}  [class_uid={class_uid}] {message}  at {list(path)}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
