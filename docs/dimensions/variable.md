# variable

`"type": "variable"` reads a value from the worker's **variable namespace** at emit time. It is the read side of the namespace; the write side is `state.variables`.

Only valid in `emitter.dimensions`. Using it in `state.variables` is a validation error — you cannot read from the namespace in the same step that writes to it.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `variable` |
| `name` | Yes | Output field name in the emitted record. |
| `variable` | Yes | The namespace key to look up. |

```json
{"name": "status", "type": "variable", "variable": "var_status"}
```

---

## The variable namespace

Every worker thread has its own **variable namespace** — a dict that persists for the lifetime of that worker's journey through the state machine. It is the mechanism by which state-side values are passed to the emitter.

```text
state.variables  ──write──►  namespace  ──read──►  emitter.dimensions (type: variable)
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

In `emitter.dimensions`, `"type": "variable"` looks up the key at emit time:

```json
{
  "name": "web_log",
  "dimensions": [
    {"name": "time",    "type": "generator:clock"},
    {"name": "user",    "type": "variable", "variable": "var_user"},
    {"name": "status",  "type": "variable", "variable": "var_status"},
    {"name": "start",   "type": "variable", "variable": "var_start"}
  ]
}
```

### Runtime error

If the referenced key has not been written into the namespace by the time the emitter runs, the engine raises a `KeyError`. `--validate` catches the case where a variable is *never* set by any state, but not the case where an execution path can reach the emitter before the state that sets it. Always write variables in a setup activity that runs before any emit state that reads them.

---

## variable:template

`"type": "variable:template"` is the multi-variable form of `variable`. Instead of reading a single key, it renders a Jinja2 template string against the full variable namespace, allowing multiple namespace values to be composed into one output field.

Only valid in `emitter.dimensions`.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `variable:template` |
| `name` | Yes | Output field name in the emitted record. |
| `template` | Yes | Jinja2 template string. Reference namespace variables by name: `{{ var_foo }}`. |

```json
{"name": "uri_path", "type": "variable:template", "template": "/assets/{{ var_category }}/{{ var_product }}_icon.png"}
```

Any Jinja2 expression or filter is valid inside the template:

```json
{"name": "feed_url", "type": "variable:template", "template": "/static/feeds/product_feed_{{ var_category }}.json"}
{"name": "label",    "type": "variable:template", "template": "{{ var_product | upper }} ({{ var_category }})"}
```

If a referenced variable is not in the namespace at emit time, the engine raises a `jinja2.UndefinedError`. The same setup-before-emit rule applies as for `variable`.
