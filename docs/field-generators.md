# Field generators

> Building a new config? See [How to build a config](./how-to-build-a-config.md) for the design process. This page is the field generator type reference.

Field generators are JSON objects that appear in emitter [`dimensions`](./emitters.md) and state [`variables`](./states.md).

Whenever a worker encounters a field generator, whether via an emitter dimension list or a state variable, it generates a key (`name`) and a value.

The value that is generated depends on the field generator `type`.

## Field generator types

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
