# Event emitters

> Building a new config? See [How to build a config](./how-to-build-a-config.md) for the design process. This page is the emitter field reference.

An emitter defines the shape of the records produced when a worker enters an [activity state](./states.md) that references it. Define one or more emitters, each with its own dimensions.

| Field | Required? | Description |
| --- | --- | --- |
| `name` | Yes | Unique name for the emitter, referenced by `"emitter": "<name>"` in activity states. |
| `dimensions` | Yes | Ordered list of dimensions. Each one defines how a single output field gets its value. |

## Dimensions

Each entry in `dimensions` answers one question: where does this field's value come from? There are three kinds:

| Kind | Type syntax | Description |
| --- | --- | --- |
| [Static](./dimensions/static.md) | `"type": "static"` | A fixed literal value, the same every time. |
| [Variable](./dimensions/variable.md) | `"type": "variable"` | The current value of a worker variable set by an earlier activity. |
| [Generator](./dimensions/generator.md) | `"type": "generator:<class>"` | A freshly sampled value, such as `generator:int`, `generator:enum`, or `generator:clock`. |

The same kinds appear in an activity's `variables` block, where they set worker variables instead of output fields. `variable` is the exception: it's valid only in `dimensions`.

Fields appear in the output record in the order they're listed in `dimensions`.

### Static

```json
{"name": "http_version", "type": "static", "value": "HTTP/1.1"}
{"name": "status", "type": "static", "value": 200}
```

The JSON value sets the output type: `"HTTP/1.1"` is a string and `200` is an integer.

### Variable

```json
{"name": "user", "type": "variable", "variable": "var_user"}
```

Worker variables are set by activity states. See [States](./states.md) for how to set them.

### Generator

```json
{"name": "time", "type": "generator:clock"}
{"name": "bytes_out", "type": "generator:int", "cardinality": 0, "distribution": {"type": "uniform", "min": 100, "max": 9000}}
```

See [Generators](./dimensions/generator.md) for the full list and each type's fields.

## Example

```json
{
  "emitters": [
    {
      "name": "web_log",
      "dimensions": [
        {"name": "time", "type": "generator:clock"},
        {"name": "user", "type": "variable", "variable": "var_user"},
        {"name": "http_method", "type": "static", "value": "GET"},
        {"name": "uri_path", "type": "variable", "variable": "var_uri_path"},
        {"name": "status", "type": "variable", "variable": "var_status"},
        {
          "name": "bytes_out", "type": "generator:int",
          "cardinality": 0,
          "distribution": {"type": "uniform", "min": 100, "max": 9000}
        },
        {
          "name": "client_ip", "type": "generator:ipaddress",
          "cardinality": 200,
          "distribution": {"type": "uniform", "min": 167772160, "max": 184549375},
          "cardinality_distribution": {"type": "uniform", "min": 0, "max": 199}
        }
      ]
    }
  ]
}
```
