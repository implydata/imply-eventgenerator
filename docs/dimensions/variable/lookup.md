# variable

`"type": "variable"` reads a single value from the worker's variable namespace at emit time.

Only valid in `emitter.dimensions`. Using it in `state.variables` is a validation error — you cannot read from the namespace in the same step that writes to it.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `variable` |
| `name` | Yes | Output field name in the emitted record. |
| `variable` | Yes | The namespace key to look up. |

```json
{"name": "status", "type": "variable", "variable": "var_status"}
{"name": "user",   "type": "variable", "variable": "var_user"}
```

If the referenced key has not been written into the namespace by the time the emitter runs, the engine raises a `KeyError`. Always write variables in a setup activity that runs before any emit state that reads them.

To compose multiple namespace values into one output field, use [`variable:template`](./template.md).

---

[← variable types](../variable.md)
