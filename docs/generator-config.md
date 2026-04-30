# Generator configurations

> Building a new config? See [How to build a config](./how-to-build-a-config.md) for the step-by-step design process. This page is the field-level reference.

A generator configuration is a JSON document passed to the generator via `-c`. Each concurrent worker (`-m`) runs one independent Actor — one lifecycle from the initial `event:start:timer` state to `event:end`.

See [`presets/configs/`](../presets/configs/) for ready-to-use examples.

| Object | Description | Options | Required? |
| --- | --- | --- | --- |
| [`states`](./states.md) | A list of states that will be used to generate events. | See [`states`](./states.md) | Yes |
| [`emitters`](./emitters.md) | A list of emitters. | See [`emitters`](./emitters.md) | Yes |
| [`templates`](./templates.md) | Named Jinja2 output templates, selected at runtime with `-t`. | See [`templates`](./templates.md) | No |

In this example, `session_start` spawns a new worker every second. Each worker emits an event via `emit_event`, waits 5 seconds in `wait_5s`, then loops back to emit again via the `route` gateway — cycling until the generator stops or the worker exits.

```json
{
  "templates": {
    "csv": {
      "header": "time,value",
      "body": "{{ time }},{{ enum_dim }}"
    }
  },
  "states": [
    {
      "name": "session_start",
      "type": "event:start:timer",
      "cardinality_distribution": { "type": "constant", "value": 1 },
      "next": "emit_event"
    },
    {
      "name": "emit_event",
      "type": "activity",
      "emitter": "example_record_1",
      "next": "wait_5s"
    },
    {
      "name": "wait_5s",
      "type": "event:intermediate:timer",
      "cardinality_distribution": { "type": "constant", "value": 5 },
      "next": "route"
    },
    {
      "name": "route",
      "type": "gateway:exclusive",
      "transitions": [
        { "next": "emit_event", "probability": 0.9 },
        { "next": "session_end", "probability": 0.1 }
      ]
    },
    { "name": "session_end", "type": "event:end" }
  ],
  "emitters": [
    {
      "name": "example_record_1",
      "dimensions": [
        { "name": "time", "type": "generator:clock" },
        {
          "name": "enum_dim",
          "type": "generator:enum",
          "values": ["A", "B", "C"],
          "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 }
        }
      ]
    }
  ]
}
```

Try this out by saving the above to `example.json`.

The following command generates 10 records with one worker, using a simulated clock:

```bash
python generator.py -c example.json -n 10 -m 1 -s "2024-01-01T00:00:00"
```

Each row is spaced 5 seconds apart, since only one worker is generating results:

```json
{"time": "2024-01-01T00:00:00+00:00", "enum_dim": "B"}
{"time": "2024-01-01T00:00:05+00:00", "enum_dim": "C"}
{"time": "2024-01-01T00:00:10+00:00", "enum_dim": "C"}
{"time": "2024-01-01T00:00:15+00:00", "enum_dim": "B"}
{"time": "2024-01-01T00:00:20+00:00", "enum_dim": "A"}
{"time": "2024-01-01T00:00:25+00:00", "enum_dim": "A"}
{"time": "2024-01-01T00:00:31+00:00", "enum_dim": "A"}
{"time": "2024-01-01T00:00:36+00:00", "enum_dim": "C"}
{"time": "2024-01-01T00:00:42+00:00", "enum_dim": "B"}
{"time": "2024-01-01T00:00:47+00:00", "enum_dim": "C"}
```

With `-m 3`, one worker is spawned per second. Rows 1–3 are each from a different worker; rows 4–6 are those same workers in their second cycle, and so on:

```json
{"time": "2024-01-01T00:00:00+00:00", "enum_dim": "B"}
{"time": "2024-01-01T00:00:01+00:00", "enum_dim": "C"}
{"time": "2024-01-01T00:00:02+00:00", "enum_dim": "C"}
{"time": "2024-01-01T00:00:05+00:00", "enum_dim": "B"}
{"time": "2024-01-01T00:00:06+00:00", "enum_dim": "A"}
{"time": "2024-01-01T00:00:07+00:00", "enum_dim": "A"}
{"time": "2024-01-01T00:00:10+00:00", "enum_dim": "A"}
{"time": "2024-01-01T00:00:11+00:00", "enum_dim": "C"}
{"time": "2024-01-01T00:00:12+00:00", "enum_dim": "B"}
{"time": "2024-01-01T00:00:15+00:00", "enum_dim": "C"}
```

With `-t csv`, the `csv` template is used and the header line is emitted once before the records:

```bash
python generator.py -c example.json -t csv -n 10 -m 1 -s "2024-01-01T00:00:00"
```

```text
time,value
2024-01-01 00:00:00+00:00,B
2024-01-01 00:00:05+00:00,C
2024-01-01 00:00:10+00:00,C
2024-01-01 00:00:15+00:00,B
2024-01-01 00:00:20+00:00,A
2024-01-01 00:00:25+00:00,A
2024-01-01 00:00:31+00:00,A
2024-01-01 00:00:36+00:00,C
2024-01-01 00:00:42+00:00,B
2024-01-01 00:00:47+00:00,C
```

## See Also

- [How to build a config](how-to-build-a-config.md) — step-by-step design guide
- [States](states.md) — state type reference
- [Emitters](emitters.md) — emitter field reference
- [Common patterns](patterns.md) — state machine patterns
- [Best practices](best-practices.md) — naming conventions and pitfalls
