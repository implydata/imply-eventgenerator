# Generators

> Building a new config? See
> [How to build a config](../how-to-build-a-config.md) for the design process.
> This page is the generator type reference.

A `generator:<class>` dimension produces a fresh value each time it's evaluated.
The part after the colon names the implementation, such as `generator:int`,
`generator:enum`, or `generator:clock`.

Generators are valid in both emitter [`dimensions`](../emitters.md), where the
value goes into the output record, and an activity's [`variables`](../states.md)
block, where the value is stored as a worker variable.

## Generator types

| Type                                              | Description                                                                                                 |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| [`generator:clock`](./generator/clock.md)         | The current simulated clock time. The record timestamp in `dimensions`; a start or end time in `variables`. |
| [`generator:enum`](./generator/enum.md)           | Selects a value from a fixed list, using a distribution as the index.                                       |
| [`generator:int`](./generator/int.md)             | Generates whole numbers from a numeric distribution.                                                        |
| [`generator:float`](./generator/float.md)         | Generates floating-point numbers, with optional decimal precision.                                          |
| [`generator:string`](./generator/string.md)       | Generates random strings of a given length from a character set.                                            |
| [`generator:ipaddress`](./generator/ipaddress.md) | Generates IPv4 addresses from a numeric distribution over the 32-bit address space.                         |
| [`generator:counter`](./generator/counter.md)     | Emits an incrementing integer. Each dimension keeps its own count.                                          |
| [`generator:timestamp`](./generator/timestamp.md) | Generates a datetime within a fixed range, independent of the simulation clock.                             |
| [`generator:object`](./generator/object.md)       | Produces a nested JSON object from a list of child dimensions.                                              |
| [`generator:list`](./generator/list.md)           | Produces a JSON array whose length and elements are drawn from distributions.                               |

## Cardinality

Most generator types support a `cardinality` field. When it's a non-zero
integer, the generator samples that many distinct values at startup and picks
among them at runtime using `cardinality_distribution`. This produces realistic
repeated values, such as the same user ID appearing across many records, instead
of a new random value every time.

Set `cardinality: 0` for a new value on every call.

## Common fields

| Field             | Required? | Description                                                                             |
| ----------------- | --------- | --------------------------------------------------------------------------------------- |
| `type`            | Yes       | `generator:<class>`, from the preceding table.                                          |
| `name`            | Yes       | The output field name (in `dimensions`) or the variable name (in `variables`).          |
| `percent_missing` | No        | Frequency (0–100) for omitting the field. Default `0`.                                  |
| `percent_nulls`   | No        | Frequency (0–100) for emitting `null`. Default `0`. Not supported by `generator:clock`. |
