# Configuration best practices

This guide provides best practices for creating maintainable, efficient, and
realistic generator configurations.

## Table of contents

1. [Development workflow](#development-workflow)
2. [Naming conventions](#naming-conventions)
3. [Configuration organization](#configuration-organization)
4. [When to use optional emitters](#when-to-use-optional-emitters)
5. [Variable design](#variable-design)
6. [State machine design](#state-machine-design)
7. [Testing and validation](#testing-and-validation)
8. [Performance considerations](#performance-considerations)
9. [Common pitfalls](#common-pitfalls)

## Development workflow

### Use synthetic clock for development

**Always use `-s` flag during development for instant feedback:**

```bash
# Development: Instant generation
python3 generator.py -c myconfig.json -n 1000 -s "2024-01-01T00:00:00" > test.json

# Production: Real-time streaming
python3 generator.py -c myconfig.json -t "2024-01-01T00:00:00" | kafka-producer ...
```

See [Testing with Synthetic Clock](patterns.md#testing-with-synthetic-clock) for
details.

### Iterative development process

1. **Start Small**: begin with 100-1000 records
2. **Validate Output**: inspect generated JSON/data
3. **Scale Up**: test with 10K-100K records
4. **Analyze Distributions**: verify statistical properties
5. **Production Deploy**: switch to real-time mode if needed

```bash
# 1. Quick validation
python3 generator.py -c config.json -n 100 -s "2024-01-01T00:00:00" | head -20

# 2. Larger test
python3 generator.py -c config.json -n 10000 -s "2024-01-01T00:00:00" > test.json

# 3. Analyze
jq '.packets' test.json | sort -n | uniq -c
jq '.bytes' test.json | awk '{sum+=$1; count++} END {print sum/count}'

# 4. Validate durations
jq -r '[.start, .end, (.end - .start)] | @csv' test.json | head -20
```

## Naming conventions

### Variables

Use descriptive prefixes to indicate scope and type:

#### Standard prefix: `var_`

All variable names should start with `var_` for consistency:

```json
{
  "variables": [
    {"name": "var_account_id", ...},
    {"name": "var_user_id", ...},
    {"name": "var_timestamp", ...}
  ]
}
```

#### Connection-level vs record-level

Use naming to indicate scope:

```json
{
  "variables": [
    // Connection-level (set once, persist)
    {"name": "var_session_id", ...},
    {"name": "var_srcaddr", ...},
    {"name": "var_dstaddr", ...},

    // Record-level (change per emission)
    {"name": "var_packets", ...},
    {"name": "var_bytes", ...},
    {"name": "var_start", ...},
    {"name": "var_end", ...}
  ]
}
```

### States

Use these prefixes consistently:

| Prefix    | State type                 | Purpose                                                |
| --------- | -------------------------- | ------------------------------------------------------ |
| `setup_*` | `activity`                 | Sets variables only, no record emitted                 |
| `emit_*`  | `activity`                 | Emits a record (with or without setting variables)     |
| `route_*` | `gateway:exclusive`        | Probabilistic routing decision                         |
| `pause_*` | `event:intermediate:timer` | Clock advance—queue wait, processing delay, dwell time |

The `event:start:timer` is named after the arrival event (`session_start`,
`ticket_arrives`). The `event:end` is named after the termination
(`session_end`, `ticket_closed`).

See [how-to-build-a-config.md](./how-to-build-a-config.md) for naming applied to
a full worked example.

### Emitters

Name emitters after the log or record type they produce: `vpc_flow_log`,
`apache_access_log`, `api_request`. Avoid generic names like `emitter1` or
`record`.

## Configuration organization

### Use comments

Add comments to explain logic that needs it:

```json
{
  "name": "emit_syn",
  "type": "activity",
  "_comment": "TCP handshake: 3 packets (SYN, SYN-ACK, ACK), ~60 bytes each",
  "emitter": "vpc_flow_log",
  "variables": [
    {"name": "var_packets", "type": "static", "value": 3},
    {"name": "var_bytes", "type": "generator:int", "distribution": {"type": "uniform", "min": 180, "max": 240}}
  ],
  "next": "session_end"
}
```

### Preset docs

Each preset has a companion doc at `docs/presets/<name>.md`. Every preset doc
must follow the standard structure described in [CLAUDE.md](../CLAUDE.md):

1. Title + one-paragraph description
2. **Quick start**—copy-paste commands covering common output formats
3. **Templates**—table of available `--template` values and their output
4. **Output fields**—table of emitted fields and descriptions
5. Preset-specific sections (product categories, session routing, per-Actor flow
   diagrams, etc.)
6. **Volume**—empirical `-w` ceiling, scaling chart, and cross-`-w`/`-i` grid
   (see [CLAUDE.md](../CLAUDE.md) for the exact structure; run
   `tools/bench_config_workers.py` and `tools/bench_grid.py` to generate)

Config JSON files live in `presets/configs/`.

## When to use optional emitters

`gateway:exclusive` and `event:intermediate:timer` states cannot have an
emitter—the validator rejects it. This is by design: routing and time-passing
are separate concerns from record emission.

For `activity` states, the `emitter` field is optional. A `setup_*` activity
that only sets variables omits it; an `emit_*` activity always includes it.

## Variable design

### Cardinality control

Use explicit value lists or bounded ranges to control cardinality. A field like
`var_account_id` drawn from `uniform(1, 1000000000)` produces a unique value on
every record—almost always wrong. Prefer a `generator:enum` with a realistic
fixed set, or a `generator:int` with `cardinality` set to the number of distinct
values you want.

### Timestamp variables

Use `generator:clock` for timestamps:

```json
{
  "name": "var_timestamp",
  "type": "generator:clock"
}
```

**Captures current simulation time** - works with both synthetic and real-time
clocks.

### IP address variables

Use CIDR notation for realistic subnets:

```json
{
  "name": "var_internal_ip",
  "type": "generator:ipaddress",
  "distribution": {"type": "cidr", "value": "10.0.0.0/16"}
}
```

**Result**: all IPs are in `10.0.0.0` - `10.0.255.255` range.

### Counter variables

Use counters for auto-incrementing IDs:

```json
{
  "name": "var_request_id",
  "type": "generator:counter",
  "start": 1000,
  "step": 1
}
```

**Result**: 1000, 1001, 1002, 1003, and so on

## State machine design

### Keep states focused

Each state should have a single clear purpose:

✅ **Good** (focused states):

```json
{
  "states": [
    {"name": "setup_session", "type": "activity", "variables": [...]},           // Setup only
    {"name": "page_timer", "type": "event:intermediate:timer", "cardinality_distribution": {...}},  // Advance clock only
    {"name": "emit_pageview", "type": "activity", "emitter": "log"}              // Emit only
  ]
}
```

❌ **Bad** (mixed concerns):

```json
{
  "name": "do_everything",
  "type": "activity",
  "emitter": "log",
  "variables": [...]  // Hard to understand/maintain when combined with a separate timer state
}
```

### Use variable persistence

Don't redefine variables unnecessarily:

✅ **Good** (persistence):

```json
{
  "states": [
    {
      "name": "setup_session",
      "type": "activity",
      "variables": [
        {"name": "var_session_id", ...}  // Defined once
      ],
      "next": "emit_page1"
    },
    {
      "name": "emit_page1",
      "type": "activity",
      "emitter": "pageview",
      "variables": [
        {"name": "var_page", "type": "static", "value": "home"}
        // var_session_id automatically available
      ],
      "next": "emit_page2"
    },
    {
      "name": "emit_page2",
      "type": "activity",
      "emitter": "pageview",
      "variables": [
        {"name": "var_page", "type": "static", "value": "products"}
        // var_session_id still available
      ],
      "next": "session_end"
    }
  ]
}
```

❌ **Bad** (redundant redefinition):

```json
{
  "states": [
    {
      "name": "page1",
      "emitter": "pageview",
      "variables": [
        {"name": "var_session_id", ...},  // Defined
        {"name": "var_page", "type": "constant", "value": "home"}
      ]
    },
    {
      "name": "page2",
      "emitter": "pageview",
      "variables": [
        {"name": "var_session_id", ...},  // Redefined unnecessarily
        {"name": "var_page", "type": "constant", "value": "products"}
      ]
    }
  ]
}
```

### Model realistic lifecycles

Use Setup→Timer→Emit for time-windowed data:

✅ **Good** (realistic duration):

```json
{
  "states": [
    {"name": "setup_flow", "type": "activity", "variables": [{"name": "var_start", "type": "generator:clock"}]},
    {"name": "flow_timer", "type": "event:intermediate:timer", "cardinality_distribution": {"type": "exponential", "mean": 5.0}},
    {"name": "emit_flow", "type": "activity", "emitter": "log", "variables": [{"name": "var_end", "type": "generator:clock"}]}
  ]
}
```

**Result**: `var_end > var_start` (realistic duration)

❌ **Bad** (instantaneous):

```json
{
  "name": "emit_flow",
  "type": "activity",
  "emitter": "log",
  "variables": [
    {"name": "var_start", "type": "generator:clock"},
    {"name": "var_end", "type": "generator:clock"}
  ]
}
```

**Problem**: `var_start == var_end` (zero duration)

See
[Flow duration with setup and timer states](patterns.md#flow-duration-with-setup-and-timer-states)
for details.

## Testing and validation

### Validate output structure

Check that emitted JSON matches expected schema:

```bash
# Generate sample
python3 generator.py -c config.json -n 100 -s "2024-01-01T00:00:00" > sample.json

# Validate required fields
jq 'select(.account_id == null)' sample.json  # Should be empty
jq 'select(.timestamp == null)' sample.json   # Should be empty

# Check field types
jq '.packets | type' sample.json | sort | uniq  # Should be "number"
```

### Validate distributions

Check that values follow expected distributions:

```bash
# Enum distribution
jq '.action' sample.json | sort | uniq -c
#  95 ACCEPT
#   5 REJECT

# Numeric ranges
jq '.bytes' sample.json | sort -n | head -1  # Min
jq '.bytes' sample.json | sort -n | tail -1  # Max

# Average
jq '.bytes' sample.json | awk '{sum+=$1; count++} END {print sum/count}'
```

### Validate temporal relationships

Check that timestamps make sense:

```bash
# Duration analysis
jq -r '[.start, .end, (.end - .start)] | @csv' sample.json > durations.csv

# Check for negative durations (BUG!)
jq 'select(.end < .start)' sample.json

# Check for zero durations (might be wrong)
jq 'select(.end == .start)' sample.json
```

### Validate cardinality

Check that cardinality is realistic:

```bash
# Unique account IDs (should be low)
jq -r '.account_id' sample.json | sort | uniq | wc -l

# Unique session IDs (should be moderate)
jq -r '.session_id' sample.json | sort | uniq | wc -l

# Unique request IDs (should equal record count)
jq -r '.request_id' sample.json | sort | uniq | wc -l
```

## Performance considerations

### Volume (`-w` and `-i`)

`-w` and `-i` together determine throughput via Little's Law—see
[Volume](../README.md#volume) in the README for the concept. The best-practice
question for config authoring: **what are you modeling, and does the resulting
concurrency ceiling—`(average session duration) / (start interval)`—seem right
for that?** A PBX with a ceiling of ~9 concurrent calls, or an e-commerce site
with a ceiling of ~2,000 concurrent shoppers, should each feel plausible for the
real system being described. If the ceiling for a config comes out oddly tiny or
huge, that's usually a sign the durations or interval you picked don't actually
reflect the real system yet—not something to shrug off. And `-i` is the primary
lever for _volume_: reaching for `-w` first when you want more data is a common
wrong instinct, since raising it past the ceiling has no effect. See Step 10 of
[how-to-build-a-config.md](how-to-build-a-config.md) for measuring the ceiling
of a preset once it's built.

### Cardinality impact

Lower cardinality = faster generation:

```json
// Faster (3 values)
{"name": "var_region", "type": "generator:enum", "values": ["us-east-1", "us-west-2", "eu-west-1"]}

// Slower (1M values)
{"name": "var_region", "type": "generator:int", "distribution": {"type": "uniform", "min": 1, "max": 1000000}}
```

### State complexity

Simpler states = faster execution:

- Prefer constant distributions when appropriate
- Minimize variables per state
- Avoid deeply nested state machines (>20 states)

## Common pitfalls

### 1. Forgetting synthetic clock

❌ **Problem**: waiting for real delays during development

```bash
# Takes hours!
python3 generator.py -c config.json -n 10000
```

✅ **Solution**: always use `-s` during development

```bash
# Instant!
python3 generator.py -c config.json -n 10000 -s "2024-01-01T00:00:00"
```

### 2. Zero-duration flows

❌ **Problem**: capturing start and end time in same state

```json
{"variables": [
  {"name": "var_start", "type": "generator:clock"},
  {"name": "var_end", "type": "generator:clock"}
]}
```

✅ **Solution**: use Start→Activity→Emit pattern

See [patterns.md](patterns.md#flow-duration-with-setup-and-timer-states)

### 3. Redefining variables unnecessarily

❌ **Problem**: duplicating variables in every state

```json
{
  "states": [
    {"name": "state1", "variables": [{"name": "var_user", ...}]},
    {"name": "state2", "variables": [{"name": "var_user", ...}]}  // Duplicate!
  ]
}
```

✅ **Solution**: define once, reuse via persistence

```json
{
  "states": [
    {"name": "state1", "variables": [{"name": "var_user", ...}]},
    {"name": "state2", "variables": []}  // var_user automatically available
  ]
}
```

### 4. Unrealistic cardinality

❌ **Problem**: too many unique values

```json
{"name": "var_user_id", "type": "generator:int", "distribution": {"type": "uniform", "min": 1, "max": 2147483647}}
```

**Result**: every record has a unique `user_id` (unrealistic).

✅ **Solution**: control cardinality with enums or limited ranges

```json
{"name": "var_user_id", "type": "generator:enum", "values": ["user1", "user2", "user3", ...]}
```

### 5. Missing variable references

❌ **Problem**: emitter references variable not defined in any state

```json
{
  "emitters": {
    "my_log": [
      {"name": "user_id", "type": "variable", "value": "var_user_id"}  // References var_user_id
    ]
  },
  "states": [
    {
      "name": "emit",
      "emitter": "my_log",
      "variables": []  // But var_user_id not defined!
    }
  ]
}
```

**Result**: `KeyError` at runtime.

✅ **Solution**: define all variables before emission

```json
{
  "states": [
    {
      "name": "setup",
      "variables": [{"name": "var_user_id", ...}]  // Define here
    },
    {
      "name": "emit",
      "emitter": "my_log",
      "variables": []  // var_user_id available via persistence
    }
  ]
}
```

### 6. Incorrect transition probabilities

❌ **Problem**: probabilities in a `gateway:exclusive` don't sum to 1.0

```json
{
  "name": "route_traffic",
  "type": "gateway:exclusive",
  "transitions": [
    {"next": "state1", "probability": 0.5},
    {"next": "state2", "probability": 0.6}  // Total = 1.1 (wrong!)
  ]
}
```

✅ **Solution**: ensure probabilities sum to exactly 1.0. `--validate` reports
this as an error.

## Summary checklist

When creating a new configuration:

- [ ] Use synthetic clock (`-s`) during development
- [ ] Use descriptive `var_` prefixed variable names
- [ ] Use descriptive state names indicating purpose
- [ ] Define common variables in a `setup_*` activity at the start
- [ ] Use Start→Activity→Emit for time-windowed data
- [ ] Control cardinality with enums or limited ranges
- [ ] Verify transition probabilities sum to 1.0
- [ ] Test with small dataset first (100-1000 records)
- [ ] Validate output structure and distributions
- [ ] Check for zero-duration flows (bug indicator)
- [ ] Document complex patterns in comments or README

For related information, see:

- [How to build a config](how-to-build-a-config.md)—step-by-step guide from
  concept to tested config
- [Common Patterns](patterns.md)—state machine patterns and techniques
- [States](states.md)—state type reference with field tables
- [Generators](dimensions/generator.md)—all generator types
