# variable types

`variable` types read from the worker's **variable namespace** at emit time. They are the read side of the namespace; the write side is `state.variables`.

Only valid in `emitter.dimensions`.

## Types

| Type | Description |
| --- | --- |
| [`variable`](./variable/lookup.md) | Reads a single namespace value by key. |
| [`variable:template`](./variable/template.md) | Composes multiple namespace values into a string via a Jinja2 template. |

---

## The variable namespace

Every worker thread has its own **variable namespace** — a dict that persists for the lifetime of that worker's journey through the state machine. It is the mechanism by which state-side values are passed to the emitter.

```text
state.variables  ──write──►  namespace  ──read──►  emitter.dimensions (type: variable*)
```

### Writing to the namespace

`state.variables` is a list of dimensions — the same format as `emitter.dimensions` — except its output goes into the namespace instead of into an emitted record. Any `static` or `generator:*` dimension is valid here.

```json
{
  "name": "setup_request", "type": "activity",
  "variables": [
    {"name": "var_status",  "type": "static",          "value": 200},
    {"name": "var_user",    "type": "generator:enum",   "values": ["alice", "bob", "carol"],
     "cardinality_distribution": {"type": "uniform", "min": 0, "max": 2}},
    {"name": "var_start",   "type": "generator:clock"}
  ],
  "emitter": "web_log", "next": "end"
}
```

Values are sampled and written into the namespace when the activity state is entered. A later state can overwrite the same key with a different value.

Values also enter the namespace via the `items` list of a [`subprocess:multi:variables`](../states/subprocess-multi-variables.md) state — the parent injects a set of variable specs before each child run.

### Reading from the namespace

In `emitter.dimensions`, use `variable` to read a single key or `variable:template` to compose several keys into one field:

```json
{
  "name": "web_log",
  "dimensions": [
    {"name": "time",     "type": "generator:clock"},
    {"name": "user",     "type": "variable",          "variable": "var_user"},
    {"name": "status",   "type": "variable",          "variable": "var_status"},
    {"name": "uri_path", "type": "variable:template", "template": "/{{ var_asset_dir }}/{{ var_asset_name }}.{{ var_asset_ext }}"}
  ]
}
```

### Runtime errors

- `variable` raises `KeyError` if the referenced key is not in the namespace.
- `variable:template` raises `jinja2.UndefinedError` if a template variable is not in the namespace.

`--validate` catches the case where a variable is *never* set by any state, but not the case where an execution path can reach the emitter before the state that sets it. Always write variables in a setup activity that runs before any emit state that reads them.
