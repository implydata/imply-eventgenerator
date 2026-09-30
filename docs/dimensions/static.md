# Static values

Use `static` to emit a fixed literal value, the same every time. The JSON value
sets the output type: a string, integer, float, or Boolean.

Valid in both emitter `dimensions` and an activity's `variables` block.

| Field             | Required? | Description                                                                    |
| ----------------- | --------- | ------------------------------------------------------------------------------ |
| `type`            | Yes       | `static`                                                                       |
| `name`            | Yes       | The output field name (in `dimensions`) or the variable name (in `variables`). |
| `value`           | Yes       | Any JSON scalar: string, integer, float, or Boolean.                           |
| `percent_missing` | No        | Frequency (0–100) for omitting the field entirely. Default `0`.                |

```json
{"name": "ident", "type": "static", "value": "-"}
{"name": "status", "type": "static", "value": 200}
{"name": "ratio", "type": "static", "value": 0.5}
{"name": "enabled", "type": "static", "value": true}
```

Use `static` instead of a `generator:string` with `chars`, a constant
`length_distribution`, and `cardinality: 0`. That combination is a workaround
for the same outcome.

## In activity variables

Different activities can set different fixed values for the same variable, and
the emitter reads whichever one was set last:

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
