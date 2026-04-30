# generator:*

A `generator:*` dimension produces a fresh value each time it is evaluated. The part after the colon names the implementation — `generator:int`, `generator:enum`, `generator:clock`, etc.

Valid in both `emitter.dimensions` (value goes into the output record) and `state.variables` (value goes into the [variable namespace](./variable.md)).

## Generator types

| Type | Description |
| --- | --- |
| [`generator:clock`](./generator/clock.md) | Current simulated clock time. Always the record timestamp in `emitter.dimensions`; useful for start/end snapshots in `state.variables`. |
| [`generator:enum`](./generator/enum.md) | Selects a value from a fixed list using a distribution as an index. |
| [`generator:int`](./generator/int.md) | Generates whole numbers from a numeric distribution. |
| [`generator:float`](./generator/float.md) | Generates floating-point numbers, with optional decimal precision. |
| [`generator:string`](./generator/string.md) | Generates random strings of a given length from a character set. |
| [`generator:ipaddress`](./generator/ipaddress.md) | Generates IPv4 addresses from a numeric distribution over the 32-bit address space. |
| [`generator:counter`](./generator/counter.md) | Emits a sequentially incrementing integer. Per-instance, not global. |
| [`generator:timestamp`](./generator/timestamp.md) | Generates a datetime within a fixed range, independent of the simulation clock. |
| [`generator:object`](./generator/object.md) | Produces a nested JSON object from a list of child dimensions. |
| [`generator:list`](./generator/list.md) | Produces a JSON array whose length and element type are drawn from distributions. |

## Cardinality

Most generator types support a `cardinality` field. When set to a non-zero integer, the generator pre-samples that many distinct values at startup and selects among them at runtime using `cardinality_distribution`. This produces realistic repeated values (the same user ID appearing across many records) rather than a fully random value on every emit.

Set `cardinality: 0` for unconstrained generation — a fresh value on every call.

## Common fields

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `generator:<class>` — see table above. |
| `name` | Yes | Output field name (in `emitter.dimensions`) or namespace key (in `state.variables`). |
| `percent_missing` | No | Frequency (0–100) for omitting the field. Default `0`. |
| `percent_nulls` | No | Frequency (0–100) for emitting `null`. Default `0`. Not supported by `generator:clock`. |
