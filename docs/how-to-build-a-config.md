# How to build a generator config

This guide walks through the full process of designing a config from scratch — from a plain-English description to a tested, working JSON file. It covers the reasoning at each step, not just the end result.

---

## Step 1 — Define the Actor

Before writing any JSON, identify the **Actor**: the single real-world entity whose lifecycle the state machine represents. One worker thread = one Actor instance. Everything in the config models what happens to one Actor from start to finish.

Ask yourself:

- What entity is generating events? (a user session, a network connection, a support ticket, an order, a sensor)
- What does "one run" of this entity look like from beginning to end?
- What data is set once at the start and carried through? (session ID, user ID, source IP)
- What data changes at each step? (current page, response code, status)

> **Example:** We want to generate support ticket data. The Actor is **a support ticket** — one ticket, from creation through triage to resolution.

---

## Step 2 — Sketch the lifecycle

Write out the lifecycle as a simple flow before touching JSON. Focus on:

- What are the distinct **phases**? (creation, waiting, processing, resolution)
- Where does **time pass** between phases? (a ticket sits in a queue — that's a timer)
- Where does **a decision** happen? (tickets are routed by priority — that's a gateway)
- Where is **an event emitted**? (when the ticket is created, when it is resolved — those are activities)

> **Example lifecycle:**
>
> ```text
> Ticket arrives
>   → Ticket created event emitted (captures ticket_id, priority, category)
>   → Sits in triage queue (1–10 minutes)
>   → Routed by priority: 30% urgent → fast-track, 70% normal → standard
>   → Fast-track: resolved in 5–15 minutes
>   → Standard: resolved in 15–60 minutes
>   → Resolution event emitted (captures agent_id, resolution_time_seconds)
>   → Done
> ```

---

## Step 3 — Map phases to state types

Each phase in your sketch maps to one of five state types, grounded in [BPMN](https://en.wikipedia.org/wiki/Business_Process_Model_and_Notation) concepts:

| What happens in this phase | State type |
| --- | --- |
| Controls how fast new tickets/sessions/connections arrive | `event:start:timer` |
| Time passes — queue wait, processing delay, flow duration | `event:intermediate:timer` |
| Something is emitted or variables are set | `activity` |
| A decision branches the path | `gateway:exclusive` |
| The lifecycle ends | `event:end` |

Apply the mapping to the example:

| Phase | State type | Name |
| --- | --- | --- |
| New ticket arrives every ~30 seconds | `event:start:timer` | `ticket_arrives` |
| Emit ticket created event | `activity` | `emit_ticket_created` |
| Sits in triage queue 1–10 min | `event:intermediate:timer` | `pause_triage_queue` |
| Route by priority | `gateway:exclusive` | `route_priority` |
| Fast-track wait 5–15 min | `event:intermediate:timer` | `pause_fast_track` |
| Standard wait 15–60 min | `event:intermediate:timer` | `pause_standard` |
| Emit resolution event | `activity` | `emit_resolved` |
| Ticket closed | `event:end` | `ticket_closed` |

> **Key rules:**
>
> - Only `event:start:timer` and `event:intermediate:timer` advance the clock. Activities and gateways are instantaneous.
> - Only `activity` states emit records or set variables.
> - `gateway:exclusive` makes a probabilistic routing decision and nothing else.
> - Every config has exactly **one** `event:start:timer` (first in the `states` list) and at least one `event:end`.

---

## Step 4 — Apply naming conventions

Use these prefixes consistently so configs are readable at a glance:

| Prefix | State type | Purpose |
| --- | --- | --- |
| `emit_*` | `activity` | Emits a record (with or without setting variables) |
| `setup_*` | `activity` | Sets variables only, no record emitted |
| `route_*` | `gateway:exclusive` | Probabilistic routing decision |
| `pause_*` | `event:intermediate:timer` | Clock advance — queue wait, processing delay, dwell time |

The `event:start:timer` is typically named after the arrival event (`ticket_arrives`, `session_start`, `connection_start`). The `event:end` is typically named after the termination (`ticket_closed`, `session_end`, `connection_end`).

---

## Step 5 — Identify variables and emitters

**Variables** are values set in an `activity` state and referenced later. They come in two kinds:

- **Session-level**: set once at the start of the lifecycle, carried through (ticket ID, user ID, source IP). Use a `setup_*` activity at the beginning, or set them in the first `emit_*` activity.
- **Step-level**: set just before they are needed (response code, bytes transferred, resolution time).

**Emitters** define the output record shape. One emitter per record type. Each dimension in an emitter either generates a fresh value or references a variable via `"type": "variable"`.

> **Example variables:**
>
> - `var_ticket_id` — set at creation, referenced at resolution
> - `var_priority` — set at creation (enum: urgent/normal/low)
> - `var_category` — set at creation (enum: billing/technical/account)
> - `var_agent_id` — set at resolution
>
> **Example emitters:**
>
> - `ticket_log` — emits `ticket_id`, `priority`, `category`, `agent_id` (using variables and fresh values)

---

## Step 6 — Choose distributions

For each timer and each generated field, choose a distribution. See [distributions.md](./distributions.md) for the full reference. Common choices:

| Situation | Distribution |
| --- | --- |
| Exact fixed value | `constant` |
| Anything equally likely in a range | `uniform` |
| Most values near the mean, tails possible | `normal` |
| Short durations most common, long tail | `exponential` |
| Realistic time-of-day traffic patterns | `gmm_temporal` |
| Fixed value field (not random at all) | `static` |

> **Example distributions:**
>
> - Interarrival (`ticket_arrives`): `exponential` mean 30s — tickets arrive roughly every 30 seconds on average
> - Triage queue wait: `uniform` 60–600s — anywhere from 1 to 10 minutes
> - Fast-track resolution: `uniform` 300–900s (5–15 min)
> - Standard resolution: `uniform` 900–3600s (15–60 min)

---

## Step 7 — Write the config

Wire everything together. The `states` list must start with the `event:start:timer`. Reference [states.md](./states.md) for the exact fields each state type requires.

```json
{
  "states": [
    {
      "name": "ticket_arrives",
      "type": "event:start:timer",
      "_comment": "New tickets arrive every ~30 seconds on average",
      "cardinality_distribution": { "type": "exponential", "mean": 30 },
      "next": "emit_ticket_created"
    },
    {
      "name": "emit_ticket_created",
      "type": "activity",
      "_comment": "Capture ticket attributes and emit the creation event",
      "emitter": "ticket_log",
      "variables": [
        {
          "name": "var_ticket_id",
          "type": "generator:int",
          "cardinality": 0,
          "distribution": { "type": "uniform", "min": 100000, "max": 999999 }
        },
        {
          "name": "var_priority",
          "type": "generator:enum",
          "values": ["urgent", "normal", "low"],
          "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 }
        },
        {
          "name": "var_category",
          "type": "generator:enum",
          "values": ["billing", "technical", "account"],
          "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 }
        },
        { "name": "var_status", "type": "static", "value": "created" }
      ],
      "next": "pause_triage_queue"
    },
    {
      "name": "pause_triage_queue",
      "type": "event:intermediate:timer",
      "_comment": "Ticket sits in queue for 1–10 minutes",
      "cardinality_distribution": { "type": "uniform", "min": 60, "max": 600 },
      "next": "route_priority"
    },
    {
      "name": "route_priority",
      "type": "gateway:exclusive",
      "_comment": "30% urgent tickets go to fast-track",
      "transitions": [
        { "next": "pause_fast_track", "probability": 0.3 },
        { "next": "pause_standard",   "probability": 0.7 }
      ]
    },
    {
      "name": "pause_fast_track",
      "type": "event:intermediate:timer",
      "_comment": "Fast-track: resolved in 5–15 minutes",
      "cardinality_distribution": { "type": "uniform", "min": 300, "max": 900 },
      "next": "emit_resolved"
    },
    {
      "name": "pause_standard",
      "type": "event:intermediate:timer",
      "_comment": "Standard: resolved in 15–60 minutes",
      "cardinality_distribution": { "type": "uniform", "min": 900, "max": 3600 },
      "next": "emit_resolved"
    },
    {
      "name": "emit_resolved",
      "type": "activity",
      "_comment": "Assign agent and emit the resolution event",
      "emitter": "ticket_log",
      "variables": [
        {
          "name": "var_agent_id",
          "type": "generator:int",
          "cardinality": 20,
          "cardinality_distribution": { "type": "uniform", "min": 0, "max": 19 },
          "distribution": { "type": "uniform", "min": 1, "max": 100 }
        },
        { "name": "var_status", "type": "static", "value": "resolved" }
      ],
      "next": "ticket_closed"
    },
    {
      "name": "ticket_closed",
      "type": "event:end"
    }
  ],
  "emitters": [
    {
      "name": "ticket_log",
      "dimensions": [
        { "name": "ticket_id",  "type": "variable", "variable": "var_ticket_id" },
        { "name": "priority",   "type": "variable", "variable": "var_priority" },
        { "name": "category",   "type": "variable", "variable": "var_category" },
        { "name": "agent_id",   "type": "variable", "variable": "var_agent_id" },
        { "name": "status",     "type": "variable", "variable": "var_status" }
      ]
    }
  ]
}
```

> **Note:** `var_agent_id` is only set in `emit_resolved`. On the `emit_ticket_created` event it will be absent from the record (variables not yet set are skipped). This is correct — the agent is not assigned at creation time.

---

## Step 8 — Run the formatter

```bash
python tools/fmt_config.py presets/configs/<name>.json
```

The formatter enforces consistent field ordering and compact/expanded forms. Always run it before committing. Run `--check` in CI.

---

## Step 9 — Test it

**Always use the synthetic clock** (`-s`). Without it, the generator runs in real time and a config with 60-minute sessions takes 60 minutes to produce data.

```bash
# Smoke test — check the first few records look right
python generator.py -c presets/configs/<name>.json -n 50 -s "2024-01-01T00:00:00" | head -10

# Full validation — run one simulated hour to surface config errors
python generator.py -c presets/configs/<name>.json -r PT1H -s "2024-01-01T00:00:00" > /tmp/test.json

# Check event counts and field distributions
python -c "
import json, collections
events = [json.loads(l) for l in open('/tmp/test.json')]
print('total events:', len(events))
print('status breakdown:', collections.Counter(e.get('status') for e in events))
print('priority breakdown:', collections.Counter(e.get('priority') for e in events))
"
```

Config errors (bad field references, wrong distributions, missing variables) often only appear after a reasonable volume of events — the PT1H test is the minimum before declaring a config done.

---

## Step 10 — Find the `-m` ceiling and document it

`-m` caps the number of simultaneously active sessions. Beyond a certain point, raising it has no effect — the worker pool is never fully used. Users need to know this ceiling so they don't set `-m` arbitrarily high and wonder why throughput doesn't increase.

**Measure it empirically** using `tools/bench_config.py`:

```bash
python tools/bench_config.py -c presets/configs/<name>.json
```

The script runs two phases — a geometric-doubling discovery pass followed by a binary-search refinement — and prints the empirical ceiling to stderr, plus a CSV table of rows vs `-m` to stdout. If the config has an ambiguous clock field, pass `--clock-field <field>`.

Document the result in the preset's `docs/presets/<name>.md` Concurrency section using direct language and include the empirical table and a Mermaid `xychart-beta`. See `docs/presets/vpc_flow_logs.md` for the canonical format.

---

## Common mistakes

| Mistake | What happens | Fix |
| --- | --- | --- |
| Putting delay in an `activity` | `activity` has no `cardinality_distribution` field — validation error | Move the delay to an `event:intermediate:timer` before the activity |
| Putting emission in a `gateway:exclusive` | Gateways cannot have an `emitter` — validation error | Route to an `activity` that emits |
| Setting variables in `event:end` | `event:end` cannot have variables — validation error | Move variable setting to the preceding `activity` |
| No `event:start:timer` | Engine raises RuntimeError at startup | Make sure the first state has `"type": "event:start:timer"` |
| Running without `-s` | Generator runs in real time — a 1-hour simulated session takes 1 real hour | Always use `-s "2024-01-01T00:00:00"` for testing |
| `-m` too high | No visible effect on throughput, confusing results | Run `tools/bench_config.py` to find the empirical ceiling and document it in the preset doc |

---

## See also

- [states.md](./states.md) — state type index with links to per-type field references
- [dimensions/generator.md](./dimensions/generator.md) — all `generator:*` types
- [distributions.md](./distributions.md) — distribution reference
- [patterns.md](./patterns.md) — common patterns (variable persistence, flow duration, multi-record sessions)
- [best-practices.md](./best-practices.md) — naming conventions and development workflow
- `presets/configs/` — real configs to read alongside this guide
