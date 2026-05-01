# Event emitters

> Building a new config? See [How to build a config](./how-to-build-a-config.md) for the design process. This page is the emitter field reference.

An emitter defines the shape of the records produced when a worker enters an activity state that references it.

| Field | Required? | Description |
| --- | --- | --- |
| `name` | Yes | Unique name for the emitter, referenced by `"emitter": "<name>"` in activity states. |
| `dimensions` | Yes | Ordered list of field descriptors — each one defines how a single output field gets its value. |

---

## Dimensions

Each entry in `dimensions` answers one question: **where does this field's value come from?** There are three kinds:

| Kind | Type syntax | Description |
| --- | --- | --- |
| [static](./dimensions/static.md) | `"type": "static"` | A fixed literal value — the same every time. |
| [variable](./dimensions/variable/lookup.md) | `"type": "variable"` | A lookup from the worker's [variable namespace](./dimensions/variable.md). |
| [variable:template](./dimensions/variable/template.md) | `"type": "variable:template"` | Composes multiple namespace values into one field via a Jinja2 template. |
| [generator](./dimensions/generator.md) | `"type": "generator:<class>"` | A freshly sampled value — `generator:int`, `generator:enum`, `generator:clock`, etc. |

Fields appear in the output record in the order they are listed in `dimensions`.

### static

```json
{"name": "http_version", "type": "static", "value": "HTTP/1.1"}
{"name": "status",       "type": "static", "value": 200}
```

The JSON value determines the type — no need to declare `string:static` vs `int:static`.

### variable

```json
{"name": "user",   "type": "variable", "variable": "var_user"}
{"name": "status", "type": "variable", "variable": "var_status"}
```

Values are written into the namespace by activity states (via `state.variables`) and by [`subprocess:multi:variables`](./states/subprocess-multi-variables.md) (via `items`). See [variable namespace](./dimensions/variable.md) for the full picture.

### generator

```json
{"name": "time",       "type": "generator:clock"}
{"name": "bytes_out",  "type": "generator:int",  "cardinality": 0, "distribution": {"type": "uniform", "min": 100, "max": 9000}}
{"name": "ip",         "type": "generator:ipaddress", "cardinality": 50, "distribution": {"type": "uniform", "min": 167772160, "max": 184549375},
                        "cardinality_distribution": {"type": "uniform", "min": 0, "max": 49}}
```

See [generator types](./dimensions/generator.md) for the full list and per-type field references.

---

## Example

```json
{
  "emitters": [
    {
      "name": "web_log",
      "dimensions": [
        {"name": "time",         "type": "generator:clock"},
        {"name": "user",         "type": "variable",          "variable": "var_user"},
        {"name": "http_method",  "type": "static",            "value": "GET"},
        {"name": "uri_path",     "type": "variable",          "variable": "var_uri_path"},
        {"name": "status",       "type": "variable",          "variable": "var_status"},
        {"name": "bytes_out",    "type": "generator:int",     "cardinality": 0,
                                  "distribution": {"type": "uniform", "min": 100, "max": 9000}},
        {"name": "client_ip",    "type": "generator:ipaddress", "cardinality": 200,
                                  "distribution": {"type": "uniform", "min": 167772160, "max": 184549375},
                                  "cardinality_distribution": {"type": "uniform", "min": 0, "max": 199}}
      ]
    }
  ]
}
```
