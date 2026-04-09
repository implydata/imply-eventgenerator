# Generator configurations

> Building a new config? See [How to build a config](./how-to-build-a-config.md) for the step-by-step design process. This page is the field-level reference.

A generator configuration is a JSON document passed to the generator via `-c`. Each concurrent worker (`-m`) runs one independent Actor — one lifecycle from the initial `event:start:timer` state to `event:end`. Activity states emit records; `event:intermediate:timer` states advance the clock without emitting.

See [`presets/configs/`](../presets/configs/) for ready-to-use examples.

| Object | Description | Options | Required? |
| --- | --- | --- | --- |
| [`states`](./states.md) | A list of states that will be used to generate events. | See [`states`](./states.md) | Yes |
| [`emitters`](./emitters.md) | A list of emitters. | See [`emitters`](./emitters.md) | Yes |

In this example there are three states. `session_start` is an `event:start:timer` that spawns a new worker every second. Each worker emits an event via `emit_event`, then waits 5 seconds in `wait_5s` before emitting again — cycling until the generator stops.

```json
{
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
      "next": "emit_event"
    }
  ],
  "emitters": [
    {
      "name": "example_record_1",
      "dimensions": [
        {
          "name": "enum_dim",
          "type": "enum",
          "values": ["A", "B", "C"],
          "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 }
        }
      ]
    }
  ]
}
```

Try this out by saving the above to `example.json`.

The following command will create 10 records and use only one worker:

```bash
python generator.py -c example.json -n 10 -m 1 -s "2024-01-01T00:00:00"
```

This causes the following output.  Notice that each row is spaced 5 seconds apart, since only one worker is generating results.

```json
{"time":"2025-02-18T09:32:16.416","enum_dim":"A"}
{"time":"2025-02-18T09:32:21.426","enum_dim":"C"}
{"time":"2025-02-18T09:32:26.429","enum_dim":"B"}
{"time":"2025-02-18T09:32:31.434","enum_dim":"C"}
{"time":"2025-02-18T09:32:36.440","enum_dim":"B"}
{"time":"2025-02-18T09:32:41.444","enum_dim":"C"}
{"time":"2025-02-18T09:32:46.449","enum_dim":"B"}
{"time":"2025-02-18T09:32:51.453","enum_dim":"A"}
{"time":"2025-02-18T09:32:56.459","enum_dim":"A"}
{"time":"2025-02-18T09:33:01.464","enum_dim":"B"}
```

When run with `-m 3`, 3 workers are spawned. Since `session_start` has a `constant` interarrival of 1 second, one worker is spawned per second, meaning rows 1–3 are each from different worker threads, rows 4–6 are those workers in their second cycle, and so on.

```json
{"time":"2025-02-18T09:35:49.618","enum_dim":"A"}
{"time":"2025-02-18T09:35:50.623","enum_dim":"B"}
{"time":"2025-02-18T09:35:51.629","enum_dim":"C"}
{"time":"2025-02-18T09:35:54.626","enum_dim":"B"}
{"time":"2025-02-18T09:35:55.626","enum_dim":"C"}
{"time":"2025-02-18T09:35:56.635","enum_dim":"A"}
{"time":"2025-02-18T09:35:59.632","enum_dim":"A"}
{"time":"2025-02-18T09:36:00.627","enum_dim":"C"}
{"time":"2025-02-18T09:36:01.640","enum_dim":"A"}
{"time":"2025-02-18T09:36:04.635","enum_dim":"A"}
```

## See Also

- [How to build a config](how-to-build-a-config.md) — step-by-step design guide
- [States](states.md) — state type reference
- [Emitters](emitters.md) — emitter field reference
- [Common patterns](patterns.md) — state machine patterns
- [Best practices](best-practices.md) — naming conventions and pitfalls
