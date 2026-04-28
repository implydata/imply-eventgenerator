# gateway:exclusive

Routes the worker to one of several next states by weighted probability. Use this to model branching paths — e.g., 40% web traffic, 25% database traffic, etc.

| Field | Description | Required? |
| --- | --- | --- |
| `name` | Unique name for this state. | Yes |
| `type` | Must be `"gateway:exclusive"`. | Yes |
| `_comment` | Optional annotation. | No |
| `transitions` | A list of possible next states and their probabilities. | Yes |

### transitions

| Field | Description | Required? |
| --- | --- | --- |
| `next` | The name of the next state. Route to an `event:end` state to terminate. | Yes |
| `probability` | Probability of this branch being taken. All probabilities must sum to 1.0. | Yes |

```json
{
  "name": "route_traffic",
  "type": "gateway:exclusive",
  "_comment": "Route to traffic type based on realistic distribution",
  "transitions": [
    { "next": "setup_web_traffic", "probability": 0.4 },
    { "next": "setup_database_traffic", "probability": 0.25 },
    { "next": "setup_ssh_traffic", "probability": 0.1 },
    { "next": "setup_internal_api", "probability": 0.2 },
    { "next": "setup_port_scan", "probability": 0.05 }
  ]
}
```

Startup validation catches probabilities that don't sum to 1.0 (±0.01 tolerance).

---

## See also

- [State types index](../states.md)
- [event:end](./event-end.md) — terminal state; a common transition target
