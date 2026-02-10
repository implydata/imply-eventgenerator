# Configuration Best Practices

This guide provides best practices for creating maintainable, efficient, and realistic generator configurations.

## Table of Contents

1. [Development Workflow](#development-workflow)
2. [Naming Conventions](#naming-conventions)
3. [Configuration Organization](#configuration-organization)
4. [When to Use Optional Emitters](#when-to-use-optional-emitters)
5. [Variable Design](#variable-design)
6. [State Machine Design](#state-machine-design)
7. [Testing and Validation](#testing-and-validation)
8. [Performance Considerations](#performance-considerations)
9. [Common Pitfalls](#common-pitfalls)

## Development Workflow

### Use Synthetic Clock for Development

**Always use `-s` flag during development for instant feedback:**

```bash
# Development: Instant generation
python3 generator.py -c myconfig.json -n 1000 -s "2024-01-01T00:00:00" > test.json

# Production: Real-time streaming
python3 generator.py -c myconfig.json -t "2024-01-01T00:00:00" | kafka-producer ...
```

See [Testing with Synthetic Clock](patterns.md#testing-with-synthetic-clock) for details.

### Iterative Development Process

1. **Start Small**: Begin with 100-1000 records
2. **Validate Output**: Inspect generated JSON/data
3. **Scale Up**: Test with 10K-100K records
4. **Analyze Distributions**: Verify statistical properties
5. **Production Deploy**: Switch to real-time mode if needed

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

## Naming Conventions

### Variables

Use descriptive prefixes to indicate scope and type:

#### Standard Prefix: `var_`

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

#### Connection-Level vs Record-Level

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

Use descriptive names that indicate purpose:

#### Pattern: `{purpose}_{phase}_{action}`

```json
{
  "states": [
    // Traffic pattern + Phase + Action
    {"name": "web_traffic_connection_setup"},
    {"name": "web_traffic_syn_activity"},
    {"name": "web_traffic_syn_emit"},

    // Generic routing/control states
    {"name": "initial"},
    {"name": "route_by_protocol"},
    {"name": "close_connection"}
  ]
}
```

#### Common State Name Patterns

- **Setup states**: `{pattern}_setup`, `{pattern}_connection_setup`
- **Activity/delay states**: `{pattern}_activity`, `{pattern}_{phase}_activity`
- **Emission states**: `{pattern}_emit`, `{pattern}_{phase}_emit`
- **Routing states**: `initial`, `route_by_{criteria}`
- **Continue states**: `{pattern}_continue`, `continue_{pattern}`
- **Termination states**: `close`, `end`, `{pattern}_close`

#### Good Examples

```json
{
  "states": [
    {"name": "initial"},
    {"name": "web_traffic_connection_setup"},
    {"name": "web_traffic_syn_activity"},
    {"name": "web_traffic_syn_emit"},
    {"name": "web_traffic_data_activity"},
    {"name": "web_traffic_data_emit"},
    {"name": "web_traffic_continue"},
    {"name": "web_traffic_fin_activity"},
    {"name": "web_traffic_fin_emit"}
  ]
}
```

#### Bad Examples

```json
{
  "states": [
    {"name": "state1"},           // Too vague
    {"name": "web"},              // Incomplete
    {"name": "emit"},             // What are we emitting?
    {"name": "do_something"}      // Not descriptive
  ]
}
```

### Emitters

Use descriptive names matching the log/record type:

```json
{
  "emitters": {
    "vpc_flow_log": [...],
    "apache_access_log": [...],
    "api_request": [...],
    "database_query": [...]
  }
}
```

Avoid generic names like `emitter1`, `log_emitter`, `record`.

## Configuration Organization

### File Structure

For complex configurations, organize logically:

```json
{
  "format": "json",
  "workers": 4,
  "emitters": {
    // Group related emitters
    "vpc_flow_log": [...],
    "routing_emitter": [...]
  },
  "states": [
    // 1. Initial/routing states
    {"name": "initial", ...},

    // 2. Group by traffic pattern
    // Web Traffic
    {"name": "web_traffic_setup", ...},
    {"name": "web_traffic_activity", ...},
    {"name": "web_traffic_emit", ...},

    // API Traffic
    {"name": "api_traffic_setup", ...},
    {"name": "api_traffic_activity", ...},
    {"name": "api_traffic_emit", ...},

    // 3. Termination states
    {"name": "close", ...}
  ]
}
```

### Use Comments

Add comments to explain non-obvious logic:

```json
{
  "name": "web_traffic_syn_emit",
  "comment": "TCP handshake: 3 packets (SYN, SYN-ACK, ACK), ~60 bytes each",
  "emitter": "vpc_flow_log",
  "variables": [
    {"name": "var_packets", "type": "constant", "value": 3},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 180, "max": 240}}
  ]
}
```

### README Files

For each generator configuration, create a companion README named `<config>_README.md` in the `conf/` directory. This allows the README to cover the generator spec, format files, and target files together. Use the following standard structure:

```text
# <Config Name> Generator

## Quick Start
One-liner commands to get output immediately — one for JSON
(gen only) and one with a format file (gen + form), if available.

## Overview
What real-world scenario this config simulates.

## Output fields
Table of dimensions and what they represent.

## State machine
The flow of states and transitions, ideally with a simple
text diagram showing the path a worker takes.

## Usage examples
Copy-paste commands to run the config with common options.

## Use cases
What this data is good for (testing, demos, analytics, etc.).

## Additional information
Any domain-specific content such as query examples, detection
scenarios, or detailed architecture notes.
```

## When to Use Optional Emitters

### Use Optional Emitters For

#### 1. Routing States

States that only choose the next path:

```json
{
  "name": "initial",
  "variables": [
    {"name": "var_account_id", ...}
  ],
  "transitions": [
    {"next": "web_traffic", "probability": 0.5},
    {"next": "api_traffic", "probability": 0.5}
  ]
}
```

**No emitter needed** - just routing logic.

#### 2. Delay/Activity States

States that only advance time:

```json
{
  "name": "flow_activity",
  "variables": [],
  "delay": {"type": "exponential", "mean": 5.0},
  "transitions": [{"next": "flow_emit", "probability": 1.0}]
}
```

**No emitter needed** - just delay for flow duration.

#### 3. Setup States

States that initialize variables without emitting:

```json
{
  "name": "connection_setup",
  "variables": [
    {"name": "var_srcaddr", ...},
    {"name": "var_dstaddr", ...},
    {"name": "var_start", "type": "clock"}
  ],
  "transitions": [{"next": "activity", "probability": 1.0}]
}
```

**No emitter needed** - just variable initialization.

### Don't Use Optional Emitters For

#### States That Should Emit Records

If the state's purpose is to produce output, always specify an emitter:

```json
{
  "name": "log_request",
  "emitter": "access_log",  // Required!
  "variables": [
    {"name": "var_status", "type": "enum", "values": [200, 404, 500]}
  ]
}
```

### Migration: Removing Dummy Emitters

If you have a configuration with dummy/routing emitters, you can remove them:

#### Before (with dummy emitter)

```json
{
  "emitters": {
    "routing_emitter": [
      {"name": "dummy", "type": "string", "distribution": {"type": "constant", "value": ""}}
    ],
    "real_log": [...]
  },
  "states": [
    {
      "name": "initial",
      "emitter": "routing_emitter",  // Dummy!
      "variables": [...]
    }
  ]
}
```

#### After (with optional emitter)

```json
{
  "emitters": {
    "real_log": [...]
  },
  "states": [
    {
      "name": "initial",
      // No emitter field - state doesn't emit
      "variables": [...]
    }
  ]
}
```

## Variable Design

### Cardinality Control

Use explicit value lists or ranges to control cardinality:

```json
{
  "name": "var_account_id",
  "type": "enum",
  "values": ["account-1", "account-2", "account-3"],
  "probabilities": [0.5, 0.3, 0.2]
}
```

**Result**: Only 3 unique account IDs (realistic for testing).

**Alternative** (too many unique values):

```json
{
  "name": "var_account_id",
  "type": "int",
  "distribution": {"type": "uniform", "min": 1, "max": 1000000000}
}
```

**Problem**: Every record has unique account ID (unrealistic).

### Timestamp Variables

Use `clock` type for timestamps:

```json
{
  "name": "var_timestamp",
  "type": "clock"
}
```

**Captures current simulation time** - works with both synthetic and real-time clocks.

### IP Address Variables

Use CIDR notation for realistic subnets:

```json
{
  "name": "var_internal_ip",
  "type": "ipaddress",
  "distribution": {"type": "cidr", "value": "10.0.0.0/16"}
}
```

**Result**: All IPs are in `10.0.0.0` - `10.0.255.255` range.

### Counter Variables

Use counters for auto-incrementing IDs:

```json
{
  "name": "var_request_id",
  "type": "counter",
  "start": 1000,
  "step": 1
}
```

**Result**: 1000, 1001, 1002, 1003, ...

## State Machine Design

### Keep States Focused

Each state should have a single clear purpose:

✅ **Good** (focused states):

```json
{
  "states": [
    {"name": "setup", "variables": [...]},      // Setup only
    {"name": "activity", "delay": {...}},       // Delay only
    {"name": "emit", "emitter": "log"}          // Emit only
  ]
}
```

❌ **Bad** (multi-purpose state):

```json
{
  "name": "do_everything",
  "emitter": "log",
  "variables": [...],  // Too much happening
  "delay": {...}       // Hard to understand/maintain
}
```

### Use Variable Persistence

Don't redefine variables unnecessarily:

✅ **Good** (persistence):

```json
{
  "states": [
    {
      "name": "setup",
      "variables": [
        {"name": "var_session_id", ...}  // Defined once
      ],
      "transitions": [{"next": "page1", "probability": 1.0}]
    },
    {
      "name": "page1",
      "emitter": "pageview",
      "variables": [
        {"name": "var_page", "type": "constant", "value": "home"}
        // var_session_id automatically available
      ]
    },
    {
      "name": "page2",
      "emitter": "pageview",
      "variables": [
        {"name": "var_page", "type": "constant", "value": "products"}
        // var_session_id still available
      ]
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

### Model Realistic Lifecycles

Use Start→Activity→Emit for time-windowed data:

✅ **Good** (realistic duration):

```json
{
  "states": [
    {"name": "start", "variables": [{"name": "var_start", "type": "clock"}]},
    {"name": "activity", "delay": {"type": "exponential", "mean": 5.0}},
    {"name": "emit", "emitter": "log", "variables": [{"name": "var_end", "type": "clock"}]}
  ]
}
```

**Result**: `var_end > var_start` (realistic duration)

❌ **Bad** (instantaneous):

```json
{
  "name": "emit",
  "emitter": "log",
  "variables": [
    {"name": "var_start", "type": "clock"},
    {"name": "var_end", "type": "clock"}
  ]
}
```

**Problem**: `var_start == var_end` (zero duration)

See [Start→Activity→Emit Pattern](patterns.md#startactivityemit-pattern-flow-duration) for details.

## Testing and Validation

### Validate Output Structure

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

### Validate Distributions

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

### Validate Temporal Relationships

Check that timestamps make sense:

```bash
# Duration analysis
jq -r '[.start, .end, (.end - .start)] | @csv' sample.json > durations.csv

# Check for negative durations (BUG!)
jq 'select(.end < .start)' sample.json

# Check for zero durations (might be wrong)
jq 'select(.end == .start)' sample.json
```

### Validate Cardinality

Check that cardinality is realistic:

```bash
# Unique account IDs (should be low)
jq -r '.account_id' sample.json | sort | uniq | wc -l

# Unique session IDs (should be moderate)
jq -r '.session_id' sample.json | sort | uniq | wc -l

# Unique request IDs (should equal record count)
jq -r '.request_id' sample.json | sort | uniq | wc -l
```

## Performance Considerations

### Workers

Use multiple workers for better throughput:

```json
{
  "workers": 4
}
```

**Rule of thumb**: Number of CPU cores for CPU-bound workloads.

### Cardinality Impact

Lower cardinality = faster generation:

```json
// Faster (3 values)
{"name": "var_region", "type": "enum", "values": ["us-east-1", "us-west-2", "eu-west-1"]}

// Slower (1M values)
{"name": "var_region", "type": "int", "distribution": {"type": "uniform", "min": 1, "max": 1000000}}
```

### State Complexity

Simpler states = faster execution:

- Prefer constant distributions when appropriate
- Minimize variables per state
- Avoid deeply nested state machines (>20 states)

## Common Pitfalls

### 1. Forgetting Synthetic Clock

❌ **Problem**: Waiting for real delays during development

```bash
# Takes hours!
python3 generator.py -c config.json -n 10000
```

✅ **Solution**: Always use `-s` during development

```bash
# Instant!
python3 generator.py -c config.json -n 10000 -s "2024-01-01T00:00:00"
```

### 2. Zero-Duration Flows

❌ **Problem**: Capturing start and end time in same state

```json
{"variables": [
  {"name": "var_start", "type": "clock"},
  {"name": "var_end", "type": "clock"}
]}
```

✅ **Solution**: Use Start→Activity→Emit pattern

See [patterns.md](patterns.md#startactivityemit-pattern-flow-duration)

### 3. Redefining Variables Unnecessarily

❌ **Problem**: Duplicating variables in every state

```json
{
  "states": [
    {"name": "state1", "variables": [{"name": "var_user", ...}]},
    {"name": "state2", "variables": [{"name": "var_user", ...}]}  // Duplicate!
  ]
}
```

✅ **Solution**: Define once, reuse via persistence

```json
{
  "states": [
    {"name": "state1", "variables": [{"name": "var_user", ...}]},
    {"name": "state2", "variables": []}  // var_user automatically available
  ]
}
```

### 4. Unrealistic Cardinality

❌ **Problem**: Too many unique values

```json
{"name": "var_user_id", "type": "int", "distribution": {"type": "uniform", "min": 1, "max": 2147483647}}
```

**Result**: Every record has unique user_id (unrealistic).

✅ **Solution**: Control cardinality with enums or limited ranges

```json
{"name": "var_user_id", "type": "enum", "values": ["user1", "user2", "user3", ...]}
```

### 5. Using Dummy Emitters

❌ **Problem**: Creating dummy emitters for routing states

```json
{
  "emitters": {
    "dummy": [{"name": "placeholder", "type": "string", "distribution": {"type": "constant", "value": ""}}]
  },
  "states": [
    {"name": "routing", "emitter": "dummy"}  // Wasteful!
  ]
}
```

✅ **Solution**: Use optional emitters (omit emitter field)

```json
{
  "states": [
    {"name": "routing"}  // No emitter field
  ]
}
```

### 6. Missing Variable References

❌ **Problem**: Emitter references variable not defined in any state

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

**Result**: KeyError at runtime.

✅ **Solution**: Define all variables before emission

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

### 7. Incorrect Transition Probabilities

❌ **Problem**: Probabilities don't sum to 1.0

```json
{
  "transitions": [
    {"next": "state1", "probability": 0.5},
    {"next": "state2", "probability": 0.6}  // Total = 1.1 (wrong!)
  ]
}
```

✅ **Solution**: Ensure probabilities sum to exactly 1.0

```json
{
  "transitions": [
    {"next": "state1", "probability": 0.5},
    {"next": "state2", "probability": 0.5}  // Total = 1.0
  ]
}
```

## Summary Checklist

When creating a new configuration:

- [ ] Use synthetic clock (`-s`) during development
- [ ] Use descriptive `var_` prefixed variable names
- [ ] Use descriptive state names indicating purpose
- [ ] Use optional emitters for routing/delay/setup states
- [ ] Define common variables in initial state
- [ ] Use Start→Activity→Emit for time-windowed data
- [ ] Control cardinality with enums or limited ranges
- [ ] Verify transition probabilities sum to 1.0
- [ ] Test with small dataset first (100-1000 records)
- [ ] Validate output structure and distributions
- [ ] Check for zero-duration flows (bug indicator)
- [ ] Document complex patterns in comments or README

For related information, see:

- [Common Patterns](patterns.md) - State machine patterns and techniques
- [Generator Specification](genspec.md) - Core concepts and field reference
- [States Documentation](genspec-states.md) - Detailed state configuration guide
