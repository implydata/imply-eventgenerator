# static

`"type": "static"` emits a fixed literal value — the same value every time. The value type is inferred from the JSON: a string, integer, float, or boolean.

Valid in both `emitter.dimensions` and `state.variables`.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `static` |
| `name` | Yes | Field name in the output record (or namespace key in `state.variables`). |
| `value` | Yes | Any JSON scalar: string, integer, float, or boolean. |
| `percent_missing` | No | Frequency (0–100) for omitting the field entirely. Default `0`. |

```json
{"name": "ident",   "type": "static", "value": "-"}
{"name": "status",  "type": "static", "value": 200}
{"name": "enabled", "type": "static", "value": true}
```

The value type is determined by the JSON literal — no need to declare `string:static` vs `int:static`. `"-"` is a string; `200` is an integer; `true` is a boolean.

## In state variables

`static` is valid in a state's `variables` block. Different states can write different constant values under the same key, and the emitter always reads from the namespace:

```json
{
  "name": "emit_success", "type": "activity",
  "variables": [
    {"name": "var_status", "type": "static", "value": 200}
  ],
  "emitter": "web_log", "next": "end"
},
{
  "name": "emit_error", "type": "activity",
  "variables": [
    {"name": "var_status", "type": "static", "value": 500}
  ],
  "emitter": "web_log", "next": "end"
}
```
