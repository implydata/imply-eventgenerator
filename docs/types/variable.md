# variable

`"type": "variable"` is a namespace read. It looks up a key in the worker's variable namespace at emit time and returns that value. The namespace must already contain the key — written by a prior activity state's `variables` block or by the parent's `items` list in a `subprocess:multi:variables` state — or a runtime `KeyError` is raised.

This is the complement to the two write mechanisms:

- [Generated variables](../variables-generated.md) — activity `variables` block writes sampled values into the namespace
- [`subprocess:multi:variables`](../states/subprocess-multi-variables.md) — each item's variable specs are evaluated and written into the namespace before the child run starts

**Context restriction**: `variable` is only valid in emitter `dimensions`. Using it in a state's `variables` list (where generated variables are used to *set* namespace values) causes a validation error — you cannot read from the namespace in the same step that writes to it.

**Runtime error**: if the referenced key has not been written into the namespace by the time the emitter runs, the generator raises a `KeyError`. `--validate` does not always catch this — if an execution path can reach the emitter before the state that writes the key, the error only appears at runtime. Always write variables in a `setup_*` activity that runs before any emit state that reads them.

| Field | Description | Possible values | Required? | Default |
| --- | --- | --- | --- | --- |
| `type` | The dimension type. | `variable` | Yes | |
| `name` | The output field name in the emitted record. | String | Yes | |
| `variable` | The namespace key to look up. | String | Yes | |

## Example

```json
{
  "states": [
    {
      "name": "session_start", "type": "event:start:timer",
      "cardinality_distribution": {"type": "constant", "value": 1},
      "next": "setup_session"
    },
    {
      "name": "setup_session", "type": "activity",
      "variables": [
        {"name": "environment", "type": "string:static", "value": "production"}
      ],
      "next": "emit_event"
    },
    {
      "name": "emit_event", "type": "activity",
      "emitter": "my_emitter",
      "next": "session_end"
    },
    {"name": "session_end", "type": "event:end"}
  ],
  "emitters": [
    {
      "name": "my_emitter",
      "dimensions": [
        {"name": "time", "type": "clock"},
        {"name": "environment", "type": "variable", "variable": "environment"}
      ]
    }
  ]
}
```

`environment` is written into the namespace by the `setup_session` activity. The emitter reads it from the namespace at emit time and returns it as the `environment` field in the record.
