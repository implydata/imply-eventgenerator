# OCSF validation

`validate.py` checks that a config's OCSF template actually produces
schema-valid [OCSF](https://schema.ocsf.io/) output. It runs the config
through `generator.py` and validates every emitted record against the real
OCSF JSON Schema — not a hand-rolled approximation of it.

## Usage

```bash
python tools/ocsf/validate.py -c presets/configs/vpc_flow_logs.json --template ocsf:network_activity
python tools/ocsf/validate.py -c presets/configs/ssh_auth.json --template ocsf:authentication -n 2000
python tools/ocsf/validate.py -c presets/configs/ecommerce.json --template ocsf:http_activity -r PT12H
```

Exits `0` if every record validates, `1` otherwise, so it can be wired into CI
alongside `tools/fmt_config.py --check`.

The OCSF class is read from each record's own `class_uid` field, so there's no
`--class` flag to get wrong (and it's the *only* correct field to use for this
— `class_name` is a human-readable caption like `"HTTP Activity"`, not the
schema's snake_case identifier; the schema library expects `http_activity`,
looked up from `class_uid` via `lookup_class_name_from_uid`).

Schemas are generated locally by the [`ocsf-json-schema`](https://github.com/nsmithuk/ocsf-json-schema)
package — no network calls once it's installed. Run `pip install -r requirements.txt`
to get it and `jsonschema`.

## Why this exists

Every `ocsf:*` template in this repo was built and proven against this exact
check before being added to a config — see the commit history for
`ecommerce.json`, `vpc_flow_logs.json`, `endpoint_network.json`, and
`ssh_auth.json`. This script formalizes what was, for the first template,
a one-off scratch script — worth doing once rather than re-deriving the same
validation approach (and re-learning the same pitfalls) for every new template.

Two pitfalls worth knowing before writing a new `ocsf:*` template:

- **`jsonschema.validate()` recompiles the schema on every call.** Over
  anything more than a handful of records this is dramatically slower than
  building one `jsonschema.Draft202012Validator(schema)` and reusing it —
  the difference observed in practice was ~40 seconds vs. 37+ minutes for the
  same ~40K records. This script already does it the fast way; if you write
  your own one-off validation snippet, don't call `validate()` in a loop.
- **Jinja's `|` filter binds tighter than arithmetic operators.** `{{ x * 1000 | int }}`
  parses as `x * (1000 | int)`, not `(x * 1000) | int` — it silently produces
  a float where OCSF requires an integer (e.g. epoch-ms `time` fields).
  Always parenthesize: `{{ (x * 1000) | int }}`.

## Field-mapping conventions used so far

These aren't rules enforced by the tool — just the choices made in the
existing templates, worth staying consistent with:

- `activity_id`/`type_uid` are derived from a source field with a small
  Jinja `set` map (e.g. HTTP method, ALLOW/DROP, Accepted/Failed password);
  `type_uid` is always `class_uid * 100 + activity_id`.
- `severity_id`/`status_id` follow success/failure of the underlying event
  (2xx/ALLOW/Accepted → success+informational; 4xx/DROP/Failed → failure+low).
- Fields with no clean OCSF slot go in `unmapped`, preserving full fidelity
  rather than dropping them.
- No OCSF profiles are used (e.g. `security_control`, `cloud`) — every
  template so far only needs base-schema fields, which keeps
  `get_class_schema()` calls simple and avoids validating against a
  profile the downstream consumer may not have loaded.
