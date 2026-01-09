# Worker states

When the worker reaches a state, the following happens:

1. [Variable](#variables) values are set.
2. If the state has an [emitter](./genspec-emitters.md), an event is emitted.
3. The generator delays for a period of time.
4. The next state is selected.

The selection of the next state is probabilistic, meaning it's possible for the output events to be stochastic (ie, they have a random probability distribution).

Each state may optionally employ an emitter. States without an emitter can be used for routing, delays, or variable setup without generating output records. The same emitter may be used by many states.

List all possible states in the `states` object of the configuration file, with the first entry in the list setting the initial state.

| Field | Description | Possible values | Required? |
| --- | --- | --- | --- |
| `name` | A unique, friendly name for this state. | | Yes |
| `emitter` | The [emitter](./genspec-emitters.md) to use. If omitted, no record is emitted. | The `name` of an emitter in the `emitter` list. | No |
| [`variables`](#variables) | A list of [field generators](./fieldgen.md). | | No |
| `delay` | How long (in seconds) to remain in the state before transitioning, defined as a [`distribution`](./distributions.md). | | Yes |
| [`transitions`](#transitions) | A list of all possible states that could be entered after this state. | | Yes |

## Variables

The optional `variables` list contains [field generators](./fieldgen.md). When a worker enters this state, it generates fields that are then stored for later re-use.

Address the variable values in `emitters` by using a `variable`-type dimension, and using the `name` of the variable in the `variable` field.

For more information, see [`variable`-type dimensions](./type-variable.md).

## Transitions

For a given state, this part of the configuration lists all the potential states that can be entered, and the probabilities for each state.

This allows for very simple (single state) through to very complex (multiple branching) state machines.

| Field | Description | Possible values | Required? |
| --- | --- | --- | --- |
| `next` | Either the name of the next state to enter _or_ `stop` | | Yes |
| `probability` | The probability that this state will be entered. | A value greater than zero and less than or equal to one. The sum total of all probabilities must be 1. | Yes |

When the `next` field is set to `stop`, the state machine will terminate.

## Examples

### Example with Emitters

In this example, there are two states, `state_1` and `state_2`.

`state_1` uses the `example_record_1` emitter, while `state_2` uses the `example_record_2` emitter.

The initial state is the first in the list, `state_1`. When `state_1` emits a record, a `delay` of 1 second occurs before a selection is made from `transitions`: there is a 50% probability that the next state will be `state_2`, and a 50% probability that the next state will be `state_1`.

If `state_2` is selected, this emits an `example_record_2`, a `delay` of 1 second occurs, and another selection is made from `transitions`: there is a 75% chance that the next state will be `state_1`, and a 25% chance that it will be `state_2`.

```json
{
  "states": [
    {
      "name": "state_1",
      "emitter": "example_record_1",
      "delay": {
        "type": "constant",
        "value": 1
      },
      "transitions": [
        {
          "next": "state_1",
          "probability": 0.5
        },
        {
          "next": "state_2",
          "probability": 0.5
        }
      ]
    },
    {
      "name": "state_2",
      "emitter": "example_record_2",
      "delay": {
        "type": "constant",
        "value": 1
      },
      "transitions": [
        {
          "next": "state_1",
          "probability": 0.75
        },
        {
          "next": "state_2",
          "probability": 0.25
        }
      ]
    }
  ],
  "emitters": [
    {
      "name": "example_record_1",
      "dimensions": [
        {
          "type": "counter",
          "name": "default_counter1"
        },
        {
          "type": "counter",
          "name": "start_counter1",
          "start": 5
        },
        {
          "type": "counter",
          "name": "increment_counter1",
          "increment": 5
        },
        {
          "type": "counter",
          "name": "both_counter1",
          "start": 5,
          "increment": 5
        }
      ]
    },
    {
      "name": "example_record_2",
      "dimensions": [
        {
          "type": "counter",
          "name": "default_counter2"
        },
        {
          "type": "counter",
          "name": "start_counter2",
          "start": 5
        },
        {
          "type": "counter",
          "name": "increment_counter2",
          "increment": 5
        },
        {
          "type": "counter",
          "name": "both_counter2",
          "start": 5,
          "increment": 5
        }
      ]
    }
  ],
  "interarrival": {
    "type": "constant",
    "value": 1
  }
}
```

Save the configuration above as `example.json`.

The following command will create 10 records and use only one worker:

```bash
python3 src/generator.py -f example.json -n 10 -m 1
```

### Example with Optional Emitters

States can omit the `emitter` field to create non-emitting states. This is useful for:

- **Routing states**: Making probabilistic decisions without emitting records
- **Delay states**: Waiting for a period of time between emissions
- **Setup states**: Initializing variables before emitting records

In this example, `route_state` doesn't emit anything - it just routes to either `emit_state_a` or `emit_state_b`:

```json
{
  "states": [
    {
      "name": "route_state",
      "_comment": "No emitter - this state routes without emitting",
      "variables": [
        {
          "type": "int",
          "name": "user_id",
          "cardinality": 0,
          "distribution": { "type": "uniform", "min": 1, "max": 1000 }
        }
      ],
      "delay": {
        "type": "constant",
        "value": 0
      },
      "transitions": [
        { "next": "emit_state_a", "probability": 0.5 },
        { "next": "emit_state_b", "probability": 0.5 }
      ]
    },
    {
      "name": "emit_state_a",
      "emitter": "record_type_a",
      "delay": { "type": "constant", "value": 1 },
      "transitions": [
        { "next": "stop", "probability": 1.0 }
      ]
    },
    {
      "name": "emit_state_b",
      "emitter": "record_type_b",
      "delay": { "type": "constant", "value": 1 },
      "transitions": [
        { "next": "stop", "probability": 1.0 }
      ]
    }
  ],
  "emitters": [
    {
      "name": "record_type_a",
      "dimensions": [
        { "type": "variable", "name": "user_id", "variable": "user_id" },
        { "type": "string", "name": "type", "cardinality": 1, "length_distribution": { "type": "constant", "value": 1 }, "chars": "A" }
      ]
    },
    {
      "name": "record_type_b",
      "dimensions": [
        { "type": "variable", "name": "user_id", "variable": "user_id" },
        { "type": "string", "name": "type", "cardinality": 1, "length_distribution": { "type": "constant", "value": 1 }, "chars": "B" }
      ]
    }
  ],
  "interarrival": { "type": "constant", "value": 1 }
}
```

In this configuration:

1. Workers start in `route_state`, which sets the `user_id` variable but doesn't emit a record
2. The worker randomly chooses either `emit_state_a` or `emit_state_b` (50% probability each)
3. The chosen state emits a record (either type A or type B) with the `user_id` from the routing state
4. The worker stops after emission

This pattern is particularly useful in complex state machines where you want to separate routing logic from data emission, such as modeling TCP connection lifecycles or multi-stage user journeys.

## See Also

- [Generator Specification](genspec.md) - Core concepts and configuration overview
- [Common Patterns](patterns.md) - State machine patterns including:
  - Variable Persistence Across States
  - Start→Activity→Emit Pattern (for realistic flow duration)
  - Multiple Records Per Connection
  - TCP Connection Lifecycle Pattern
- [Best Practices](best-practices.md) - Configuration guidelines and naming conventions
