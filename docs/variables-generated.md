# Variables — generated

> Building a new config? See [How to build a config](./how-to-build-a-config.md) for the design process. This page is the reference for all generated variable types.

The variable namespace is a per-worker dict that persists for the lifetime of each worker lifecycle. Generated variables are one of two ways to write values into that namespace — the other is [injected variables](./variables-injected.md).

A generated variable is declared in the `variables` list of an `activity` state. Each entry specifies a `name` (the namespace key) and a `type` that controls how the value is produced. The value is sampled at runtime when the state is entered, and stored in the namespace under that name.

The same generator types also appear directly in emitter `dimensions`, where they produce a value straight into the output record rather than into the namespace. The distinction is context: `variables` block → writes to namespace; `dimensions` block → writes to record.

## Generator types

| Type | Description |
| --- | --- |
| [`clock`](./types/clock.md) | Emits the current simulated clock time as the event timestamp. |
| [`timestamp`](./types/timestamp.md) | Generates a datetime between a range. |
| [`string:static`](./types/string_static.md) | Emits a fixed literal string — the same value every time. |
| [`int:static`](./types/int_static.md) | Emits a fixed literal integer — the same value every time. |
| [`string`](./types/string.md) | Creates a synthetic string, optionally limited to a specific list of characters. |
| [`int`](./types/int.md) | Generates whole numbers. |
| [`float`](./types/float.md) | Generates floating point numbers. |
| [`ipaddress`](./types/ipaddress.md) | Creates a network IP address. |
| [`counter`](./types/counter.md) | Creates an incrementing integer. |
| [`enum`](./types/enum.md) | Selects a value from a fixed list. |
| [`object`](./types/object.md) | Produces a nested JSON object. |
| [`list`](./types/list.md) | Produces an array of values. |
