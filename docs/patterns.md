# Common State Machine Patterns

This guide documents common patterns and techniques for building realistic state machine configurations. These patterns were discovered while creating production-quality synthetic data generators and represent best practices for achieving realistic, efficient configurations.

## Table of Contents

1. [Variable Persistence Across States](#variable-persistence-across-states)
2. [Flow Duration with Setup and Timer States](#flow-duration-with-setup-and-timer-states)
3. [Common Variables in Initial State](#common-variables-in-initial-state)
4. [Multiple Records Per Connection](#multiple-records-per-connection)
5. [TCP Connection Lifecycle Pattern](#tcp-connection-lifecycle-pattern)
6. [Testing with Synthetic Clock](#testing-with-synthetic-clock)

## Variable Persistence Across States

### Key Concept

**Key Insight:** Variables set in one state automatically persist to all subsequent states within the same worker thread. You only need to redefine variables that change.

This is one of the most important concepts for building efficient state machines. Understanding variable persistence allows you to:

- Avoid unnecessary variable redefinitions
- Build complex state machines without repetition
- Create cleaner, more maintainable configurations

### Basic Example

```json
{
  "states": [
    {
      "name": "setup_session",
      "type": "activity",
      "variables": [
        {"name": "var_user_id", "type": "int", "cardinality": 0, "distribution": {"type": "uniform", "min": 1000, "max": 9999}},
        {"name": "var_session_id", "type": "int", "cardinality": 0, "distribution": {"type": "uniform", "min": 100000, "max": 999999}}
      ],
      "next": "emit_page_view"
    },
    {
      "name": "emit_page_view",
      "type": "activity",
      "emitter": "web_event",
      "variables": [
        {"name": "var_page_name", "type": "enum", "values": ["home", "products", "checkout"],
         "cardinality_distribution": {"type": "uniform", "min": 0, "max": 2}}
        // var_user_id and var_session_id automatically available here!
      ],
      "next": "route_continue"
    },
    {
      "name": "route_continue",
      "type": "gateway:exclusive",
      "transitions": [
        {"next": "emit_page_view", "probability": 0.7},
        {"next": "session_end", "probability": 0.3}
      ]
    },
    {
      "name": "session_end",
      "type": "event:end"
    }
  ]
}
```

### How It Works

1. **`setup_session` activity**: Sets `var_user_id` and `var_session_id` once for the Actor's lifetime
2. **`emit_page_view` activity**: References `var_user_id` and `var_session_id` without redefining them
3. **Actor scope**: Variables persist for the lifetime of the Actor instance (one worker thread)
4. **Only redefine what changes**: Only define new variables or variables whose values should change between states

### Common Use Cases

- **Connection-level attributes**: IP addresses, user IDs, session IDs
- **Transaction attributes**: Order IDs, customer information
- **Flow attributes**: Source/destination addresses, ports

### Example: VPC Flow Logs

```json
{
  "states": [
    {
      "name": "setup_connection",
      "type": "activity",
      "variables": [
        {"name": "var_account_id", "type": "enum", "values": ["123456789012", "123456789013"],
         "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}},
        {"name": "var_interface_id", "type": "enum", "values": ["eni-1a2b3c4d", "eni-5e6f7g8h"],
         "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}},
        {"name": "var_action", "type": "enum", "values": ["ACCEPT", "REJECT"],
         "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}}
      ],
      "next": "route_traffic_type"
    },
    {
      "name": "route_traffic_type",
      "type": "gateway:exclusive",
      "transitions": [
        {"next": "setup_web_traffic", "probability": 0.4},
        {"next": "setup_api_traffic", "probability": 0.6}
      ]
    },
    {
      "name": "setup_web_traffic",
      "type": "activity",
      "variables": [
        {"name": "var_srcaddr", "type": "ipaddress", "distribution": {"type": "uniform", "min": 167772160, "max": 184549375}, "cardinality": 0},
        {"name": "var_srcport", "type": "int", "distribution": {"type": "uniform", "min": 1024, "max": 65535}, "cardinality": 0},
        {"name": "var_dstport", "type": "int:static", "value": 443}
        // var_account_id, var_interface_id, var_action all available here!
      ],
      "next": "web_traffic_emit"
    }
  ]
}
```

### Benefits

✅ **Reduced Configuration Size**: 20-30% smaller configs for complex state machines
✅ **Easier Maintenance**: Change common variables in one place
✅ **Better Performance**: Fewer variable computations per state
✅ **Clearer Intent**: Shows which variables are connection-wide vs state-specific

## Flow Duration with Setup and Timer States

### Problem and Solution

**Problem:** When modeling events with duration (network flows, sessions, transactions), both start and end times must be captured, but a delay must occur between them. This requires the start time to be captured before the delay and the end time after.

**Solution:** Use a two-state pattern: a `setup_*` activity state that sets variables (including `var_start`), followed by an `event:intermediate:timer` state for the delay. The `emit_*` activity after the timer captures `var_end` and emits the record.

This is the **most important pattern for time-windowed data** like network flows, session logs, or transaction records.

### Execution Pattern

When modeling a flow with duration, execution happens across three states:

1. **`setup_*` activity** — captures `var_start` and any connection attributes (no emitter)
2. **`event:intermediate:timer`** — the delay; time advances
3. **`emit_*` activity** — captures `var_end`, emits the record

This ensures that `var_start` and `var_end` have different values, creating realistic duration.

### Two-State Example

```json
{
  "states": [
    {
      "name": "setup_web_syn",
      "type": "activity",
      "variables": [
        {"name": "var_start", "type": "clock"},
        {"name": "var_srcaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "10.0.0.0/16"}},
        {"name": "var_dstaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "203.0.113.0/24"}},
        {"name": "var_srcport", "type": "int", "distribution": {"type": "uniform", "min": 1024, "max": 65535}},
        {"name": "var_dstport", "type": "constant", "value": 443}
      ],
      "next": "timer_web_syn"
    },
    {
      "name": "timer_web_syn",
      "type": "event:intermediate:timer",
      "cardinality_distribution": {"type": "uniform", "min": 1.0, "max": 2.0},
      "next": "emit_web_syn"
    },
    {
      "name": "emit_web_syn",
      "type": "activity",
      "variables": [
        {"name": "var_end", "type": "clock"},
        {"name": "var_packets", "type": "constant", "value": 3},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 180, "max": 240}}
      ],
      "emitter": "vpc_flow_log",
      "next": "web_traffic_data_setup"
    }
  ]
}
```

### Why This Works

1. Worker enters `setup_web_syn`: `var_start = T₀`, plus the connection 5-tuple are captured
2. Worker enters `timer_web_syn`: time advances by 1.0–2.0 seconds
3. Worker enters `emit_web_syn`: `var_end = T₀ + 1.5 seconds` (example), record emitted with `start < end`

### Without This Pattern (Anti-Pattern)

```json
{
  "name": "flow_bad",
  "type": "activity",
  "variables": [
    {"name": "var_start", "type": "clock"},
    {"name": "var_end", "type": "clock"}
    // Both sampled at the same instant — start == end (unrealistic)
  ],
  "emitter": "flow_record"
}
```

**Problem**: Both `var_start` and `var_end` are sampled at the same instant, resulting in zero-duration flows.

### Use Cases

- **Network flow logs** (VPC Flow Logs, NetFlow, sFlow)
- **Session logs** (web sessions, API sessions)
- **Transaction logs** (database transactions, API transactions)
- **Call detail records** (phone calls, video conferences)
- **Any event with a meaningful duration**

### VPC Flow Logs Example

A data-transfer state using the setup+timer+emit pattern:

```json
{
  "name": "setup_web_data",
  "type": "activity",
  "variables": [
    {"name": "var_start", "type": "clock"}
  ],
  "next": "timer_web_data"
},
{
  "name": "timer_web_data",
  "type": "event:intermediate:timer",
  "cardinality_distribution": {"type": "uniform", "min": 5.0, "max": 30.0},
  "next": "emit_web_data"
},
{
  "name": "emit_web_data",
  "type": "activity",
  "variables": [
    {"name": "var_end", "type": "clock"},
    {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 50, "max": 500}},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 5000, "max": 500000}}
  ],
  "emitter": "vpc_flow_log",
  "next": "route_web_data_continue"
}
```

**Result**: Flow records with realistic duration of 5–30 seconds, capturing actual data transfer time.

### Key Benefits

✅ **Realistic Time Windows**: Events have proper duration (start < end)
✅ **Clear Separation of Concerns**: Setup, wait, and emit are distinct states
✅ **Accurate Metrics**: Can model throughput, packets/bytes over time
✅ **Protocol Accuracy**: Models real-world connection lifecycles
✅ **Testable**: Easy to verify duration ranges in generated data

### When to Use the Setup State

Use the `setup_*` activity to:

- Capture start time before a delay
- Set up connection attributes (IP addresses, ports) that are used throughout the flow
- Initialize any variable that should reflect the state entry time rather than emission time

Use the `emit_*` activity for:

- Capturing end time after the timer delay
- Computing metrics that depend on the delay (packets, bytes transferred)
- Emitting the record with the emitter field

## Common Variables in Initial State

### Optimization Strategy

**Optimization:** Move variables that are common across all execution paths to the initial routing state. This reduces configuration size and makes intent clearer.

This pattern builds on [Variable Persistence](#variable-persistence-across-states) to optimize large state machines with multiple traffic patterns.

### Before and After Comparison

#### Before Optimization

```json
{
  "states": [
    {
      "name": "route_traffic",
      "type": "gateway:exclusive",
      "transitions": [
        {"next": "emit_web_traffic", "probability": 0.4},
        {"next": "emit_api_traffic", "probability": 0.6}
      ]
    },
    {
      "name": "emit_web_traffic",
      "type": "activity",
      "emitter": "access_log",
      "variables": [
        {"name": "var_account_id", "type": "enum", "values": ["account-1", "account-2"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}},
        {"name": "var_region", "type": "enum", "values": ["us-east-1", "us-west-2"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}},
        {"name": "var_url", "type": "enum", "values": ["/home", "/products"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}}
      ],
      "next": "session_end"
    },
    {
      "name": "emit_api_traffic",
      "type": "activity",
      "emitter": "api_log",
      "variables": [
        {"name": "var_account_id", "type": "enum", "values": ["account-1", "account-2"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}},
        {"name": "var_region", "type": "enum", "values": ["us-east-1", "us-west-2"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}},
        {"name": "var_endpoint", "type": "enum", "values": ["/api/v1/users", "/api/v1/orders"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}}
      ],
      "next": "session_end"
    }
  ]
}
```

**Problem**: `var_account_id` and `var_region` are duplicated in both activities.

#### After Optimization

```json
{
  "states": [
    {
      "name": "setup_session",
      "type": "activity",
      "variables": [
        {"name": "var_account_id", "type": "enum", "values": ["account-1", "account-2"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}},
        {"name": "var_region", "type": "enum", "values": ["us-east-1", "us-west-2"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}}
      ],
      "next": "route_traffic"
    },
    {
      "name": "route_traffic",
      "type": "gateway:exclusive",
      "transitions": [
        {"next": "emit_web_traffic", "probability": 0.4},
        {"next": "emit_api_traffic", "probability": 0.6}
      ]
    },
    {
      "name": "emit_web_traffic",
      "type": "activity",
      "emitter": "access_log",
      "variables": [
        {"name": "var_url", "type": "enum", "values": ["/home", "/products"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}}
      ],
      "next": "session_end"
    },
    {
      "name": "emit_api_traffic",
      "type": "activity",
      "emitter": "api_log",
      "variables": [
        {"name": "var_endpoint", "type": "enum", "values": ["/api/v1/users", "/api/v1/orders"], "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}}
      ],
      "next": "session_end"
    }
  ]
}
```

**Benefit**: `var_account_id` and `var_region` are defined once in `setup_session` and automatically available in both activity states.

### VPC Flow Logs: Common Variables

The VPC Flow Logs configuration has multiple traffic patterns (web, API, database, DNS, SSH, rejected traffic, port scans). Variables common to **all** flows were moved to the initial state:

```json
{
  "name": "setup_connection",
  "type": "activity",
  "variables": [
    {
      "name": "var_account_id",
      "type": "enum",
      "values": ["123456789012", "123456789013", "123456789014"],
      "cardinality_distribution": {"type": "uniform", "min": 0, "max": 2}
    },
    {
      "name": "var_interface_id",
      "type": "enum",
      "values": [
        "eni-0a1b2c3d4e5f60001", "eni-0a1b2c3d4e5f60002",
        "eni-0a1b2c3d4e5f60003", "eni-0a1b2c3d4e5f60004",
        "eni-0a1b2c3d4e5f60005", "eni-0a1b2c3d4e5f60006"
      ],
      "cardinality_distribution": {"type": "exponential", "mean": 2},
      "_comment": "ENI selected once per connection — all flow records use same interface"
    },
    {
      "name": "var_action",
      "type": "enum",
      "values": ["ACCEPT", "REJECT"],
      "cardinality_distribution": {"type": "uniform", "min": 0, "max": 1}
    }
  ],
  "next": "route_traffic_type"
},
{
  "name": "route_traffic_type",
  "type": "gateway:exclusive",
  "transitions": [
    {"next": "web_traffic_syn", "probability": 0.35},
    {"next": "database_traffic_syn", "probability": 0.25},
    {"next": "ssh_traffic_syn", "probability": 0.15},
    {"next": "internal_api_syn", "probability": 0.10},
    {"next": "port_scan", "probability": 0.10},
    {"next": "dns_traffic", "probability": 0.05}
  ]
}
```

### Connection-Level vs Flow-Level Variables

A critical design decision is whether a variable should be:

- **Connection-level** (set once in initial state, persists across all flow records)
- **Flow-level** (set in each state, can vary between flow records)

#### ENI Example: Connection-Level is Correct

In AWS VPC Flow Logs, the Elastic Network Interface (ENI) is the network observer. A single connection (defined by its 5-tuple: src/dst IP, src/dst port, protocol) is always observed by the **same ENI** across all its flow records.

**Correct** (ENI in initial state):

```json
{
  "name": "initial",
  "variables": [
    {"name": "var_interface_id", "type": "enum", "values": ["eni-001", "eni-002"]}
  ]
}
```

**Result**: All flow records for the same connection have the same ENI (100% consistency).

**Incorrect** (ENI in each traffic state):

```json
{
  "name": "web_traffic_syn",
  "variables": [
    {"name": "var_interface_id", "type": "enum", "values": ["eni-001", "eni-002"]},
    {"name": "var_start", "type": "clock"}
  ]
}
```

**Problem**: Each flow record randomly selects a new ENI. A connection with 3 flow records (SYN, DATA, FIN) could show different ENIs for each record, which is impossible in real AWS infrastructure.

#### When to Use Connection-Level Variables

Place variables in the initial state when they represent:

- **Infrastructure attributes**: Network interfaces, VPCs, subnets, availability zones
- **Connection identity**: Source/destination IPs and ports (for multi-record connections)
- **Session attributes**: User IDs, session IDs, customer IDs
- **Account/tenant context**: AWS account IDs, organization IDs
- **Any attribute that should remain constant across all records for the same connection**

#### When to Use Flow-Level Variables

Set variables in individual states when they represent:

- **Time-varying metrics**: Packet counts, byte counts that change per flow record
- **Temporal boundaries**: Start/end times that differ for each aggregation window
- **State-specific attributes**: TCP flags, connection state that changes over lifecycle

### How to Identify Common Variables

Ask yourself:

1. **Does this variable appear in all traffic patterns?** → Move to initial state
2. **Does this variable have the same distribution everywhere?** → Move to initial state
3. **Is this variable connection-level rather than pattern-specific?** → Move to initial state

### Common Variable Benefits

✅ **Reduced Configuration Size**: 20-30% reduction for complex state machines
✅ **Single Source of Truth**: Change common variables in one place
✅ **Clearer Intent**: Immediately shows which variables are global vs pattern-specific
✅ **Easier Maintenance**: Add new traffic patterns without duplicating common variables

### Caution

Only move variables that are **truly common** across all paths. If a variable differs in distribution or values between patterns, keep it pattern-specific.

## Multiple Records Per Connection

### Overview

Real-world connections often generate multiple observation records over time. Examples:

- **VPC Flow Logs**: Multiple 60-second aggregation windows for the same connection
- **Session Logs**: Multiple events (pageviews, clicks) for the same session
- **Transaction Logs**: Multiple line items for the same order

**Pattern:** Use a continue/loop state to emit multiple records for the same connection.

### State Flow Diagram

```text
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ Emit Record  │───70%─▶│ Close        │        │              │
│              │        │ Connection   │        │              │
│              │        │              │        │              │
│              │───30%─▶│ Continue     │───────▶│ Setup        │─┐
│              │        │ Connection   │        │ State        │ │
│              │◀───────┴──────────────┴────────┴──────────────┘ │
└──────────────┘                                                 │
       ▲                                                          │
       └──────────────────────────────────────────────────────────┘
```

### Configuration Example

```json
{
  "states": [
    {
      "name": "connection_setup",
      "type": "activity",
      "variables": [
        {"name": "var_srcaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "10.0.0.0/16"}},
        {"name": "var_dstaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "203.0.113.0/24"}},
        {"name": "var_srcport", "type": "int", "distribution": {"type": "uniform", "min": 1024, "max": 65535}},
        {"name": "var_dstport", "type": "constant", "value": 443}
      ],
      "next": "setup_flow_record"
    },
    {
      "name": "setup_flow_record",
      "type": "activity",
      "variables": [
        {"name": "var_start", "type": "clock"}
      ],
      "next": "timer_flow_record"
    },
    {
      "name": "timer_flow_record",
      "type": "event:intermediate:timer",
      "cardinality_distribution": {"type": "exponential", "mean": 60.0},
      "next": "emit_flow_record"
    },
    {
      "name": "emit_flow_record",
      "type": "activity",
      "variables": [
        {"name": "var_end", "type": "clock"},
        {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 100, "max": 10000}},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 10000, "max": 1000000}}
      ],
      "emitter": "flow_log",
      "next": "route_flow_continue"
    },
    {
      "name": "route_flow_continue",
      "type": "gateway:exclusive",
      "transitions": [
        {"next": "connection_end", "probability": 0.7},
        {"next": "setup_flow_record", "probability": 0.3}
      ]
    },
    {
      "name": "connection_end",
      "type": "event:end"
    }
  ]
}
```

### How Multi-record Works

1. **Connection Setup**: Sets the 5-tuple (src/dst addr/port) once at the start
2. **Setup State**: Captures `var_start` before the timer
3. **Timer State**: Time advances (simulating data transfer duration)
4. **Emit State**: Captures `var_end`, emits the flow record
5. **Decision Point**: 30% chance to loop back to `setup_flow_record`, 70% chance to reach `event:end`
6. **Same Connection**: Source/destination IPs and ports persist across all records
7. **Result**: Same 5-tuple appears in multiple flow records with different time windows

### Real-World Multi-record Example: VPC Flow Logs

From the actual VPC Flow Logs configuration, the data transfer state shows how multiple flow records are generated for the same connection, using the setup+timer+emit pattern:

```json
{
  "name": "setup_web_data",
  "type": "activity",
  "variables": [
    {"name": "var_start", "type": "clock"}
  ],
  "next": "timer_web_data"
},
{
  "name": "timer_web_data",
  "type": "event:intermediate:timer",
  "cardinality_distribution": {"type": "uniform", "min": 5.0, "max": 30.0},
  "next": "emit_web_data"
},
{
  "name": "emit_web_data",
  "type": "activity",
  "variables": [
    {"name": "var_end", "type": "clock"},
    {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 50, "max": 500}},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 5000, "max": 500000}}
  ],
  "emitter": "vpc_flow_log",
  "next": "route_web_data"
},
{
  "name": "route_web_data",
  "type": "gateway:exclusive",
  "transitions": [
    {"next": "web_traffic_fin", "probability": 0.5},
    {"next": "setup_web_data", "probability": 0.5}
  ]
}
```

**Key points:**

- 50% chance to move to FIN (connection teardown)
- 50% chance to loop back to `setup_web_data` for another data transfer record
- Each loop generates a new flow record with a fresh 5–30 second window
- The connection 5-tuple (src/dst IPs and ports) persists across all records

### Multi-record Variations

#### Increasing Probability of Closure

Make long-running connections less likely by using a separate `gateway:exclusive` after each emit with escalating exit probabilities:

```json
{
  "name": "route_after_record_1",
  "type": "gateway:exclusive",
  "transitions": [
    {"next": "connection_end", "probability": 0.5},
    {"next": "setup_record_2", "probability": 0.5}
  ]
},
{
  "name": "emit_record_2",
  "type": "activity",
  "emitter": "flow_log",
  "variables": [...],
  "next": "route_after_record_2"
},
{
  "name": "route_after_record_2",
  "type": "gateway:exclusive",
  "transitions": [
    {"next": "connection_end", "probability": 0.7},
    {"next": "setup_record_3", "probability": 0.3}
  ]
},
{
  "name": "emit_record_3",
  "type": "activity",
  "emitter": "flow_log",
  "variables": [...],
  "next": "route_after_record_3"
},
{
  "name": "route_after_record_3",
  "type": "gateway:exclusive",
  "transitions": [
    {"next": "connection_end", "probability": 0.9},
    {"next": "setup_record_4", "probability": 0.1}
  ]
}
```

**Result**: Most connections emit 1-2 records, fewer emit 3+, very few emit 4+.

#### Session Events (Multiple Event Types)

```json
{
  "name": "emit_pageview",
  "type": "activity",
  "emitter": "session_event",
  "variables": [
    {"name": "var_event_type", "type": "string:static", "value": "pageview"},
    {"name": "var_page_url", "type": "enum", "values": ["/home", "/products", "/checkout"],
     "cardinality_distribution": {"type": "uniform", "min": 0, "max": 2}}
  ],
  "next": "route_after_pageview"
},
{
  "name": "route_after_pageview",
  "type": "gateway:exclusive",
  "transitions": [
    {"next": "session_end", "probability": 0.2},
    {"next": "emit_click", "probability": 0.5},
    {"next": "emit_pageview", "probability": 0.3}
  ]
},
{
  "name": "emit_click",
  "type": "activity",
  "emitter": "session_event",
  "variables": [
    {"name": "var_event_type", "type": "string:static", "value": "click"},
    {"name": "var_button_id", "type": "enum", "values": ["add_to_cart", "buy_now", "learn_more"],
     "cardinality_distribution": {"type": "uniform", "min": 0, "max": 2}}
  ],
  "next": "route_after_click"
},
{
  "name": "route_after_click",
  "type": "gateway:exclusive",
  "transitions": [
    {"next": "session_end", "probability": 0.3},
    {"next": "emit_pageview", "probability": 0.7}
  ]
}
```

**Result**: Same `session_id` (persisted variable) appears across multiple events of different types.

### Session Event Benefits

✅ **Realistic Connection Lifetimes**: Models long-running connections accurately
✅ **Temporal Correlation**: Same connection attributes across multiple records
✅ **Aggregation Testing**: Perfect for testing time-series aggregations
✅ **Cardinality Control**: More records without more unique connections

## TCP Connection Lifecycle Pattern

### TCP Lifecycle Overview

Real TCP connections have distinct phases with different characteristics:

- **SYN** (Handshake): 3 packets, ~180-240 bytes
- **Data Transfer**: Variable packets/bytes depending on payload
- **FIN** (Graceful close): 2 packets, ~120-180 bytes
- **RST** (Abrupt close): 1 packet, ~60 bytes

Modeling these phases creates realistic network flow data for security analysis, capacity planning, and anomaly detection.

### TCP Lifecycle Pattern

```text
Connection
    │
    ▼
┌────────────┐
│ SYN Phase  │──95%──▶┌──────────────┐──100%──▶┌──────────────┐──50%──▶┌──────────────┐
│ 3 packets  │        │ Data Transfer│          │ FIN Phase    │        │ Close        │
│ ~180 bytes │        │ Variable     │          │ 2 packets    │        │              │
└────────────┘        │ packets/bytes│          │ ~120 bytes   │        └──────────────┘
    │                 └──────────────┘          └──────────────┘
    │                                                  │
    │                                                  │
    │                                             Continue (50%)
    │                                                  │
    │                                                  ▼
    5%──▶┌──────────────┐                    ┌──────────────┐
         │ RST Phase    │                    │ More Data    │
         │ 1 packet     │                    │ Transfer     │
         │ ~60 bytes    │                    └──────────────┘
         └──────────────┘
```

### TCP Lifecycle Configuration Example

Each TCP phase uses the setup+timer+emit pattern: a `setup_*` activity captures `var_start`, an `event:intermediate:timer` state provides the delay, and an `emit_*` activity captures `var_end` and emits the record.

```json
{
  "states": [
    {
      "name": "setup_tcp_connection",
      "type": "activity",
      "variables": [
        {"name": "var_srcaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "10.0.0.0/16"}},
        {"name": "var_dstaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "203.0.113.0/24"}},
        {"name": "var_srcport", "type": "int", "distribution": {"type": "uniform", "min": 1024, "max": 65535}},
        {"name": "var_dstport", "type": "constant", "value": 443},
        {"name": "var_start", "type": "clock"}
      ],
      "next": "timer_tcp_syn"
    },
    {
      "name": "timer_tcp_syn",
      "type": "event:intermediate:timer",
      "cardinality_distribution": {"type": "exponential", "mean": 0.1},
      "next": "emit_tcp_syn"
    },
    {
      "name": "emit_tcp_syn",
      "type": "activity",
      "variables": [
        {"name": "var_end", "type": "clock"},
        {"name": "var_packets", "type": "constant", "value": 3},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 180, "max": 240}}
      ],
      "emitter": "tcp_flow",
      "next": "route_tcp_syn"
    },
    {
      "name": "route_tcp_syn",
      "type": "gateway:exclusive",
      "transitions": [
        {"next": "setup_tcp_data", "probability": 0.95},
        {"next": "setup_tcp_rst", "probability": 0.05}
      ]
    },
    {
      "name": "setup_tcp_data",
      "type": "activity",
      "variables": [
        {"name": "var_start", "type": "clock"}
      ],
      "next": "timer_tcp_data"
    },
    {
      "name": "timer_tcp_data",
      "type": "event:intermediate:timer",
      "cardinality_distribution": {"type": "exponential", "mean": 5.0},
      "next": "emit_tcp_data"
    },
    {
      "name": "emit_tcp_data",
      "type": "activity",
      "variables": [
        {"name": "var_end", "type": "clock"},
        {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 50, "max": 500}},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 5000, "max": 500000}}
      ],
      "emitter": "tcp_flow",
      "next": "route_tcp_data"
    },
    {
      "name": "route_tcp_data",
      "type": "gateway:exclusive",
      "transitions": [
        {"next": "setup_tcp_fin", "probability": 0.5},
        {"next": "setup_tcp_data", "probability": 0.5}
      ]
    },
    {
      "name": "setup_tcp_fin",
      "type": "activity",
      "variables": [
        {"name": "var_start", "type": "clock"}
      ],
      "next": "timer_tcp_fin"
    },
    {
      "name": "timer_tcp_fin",
      "type": "event:intermediate:timer",
      "cardinality_distribution": {"type": "exponential", "mean": 0.1},
      "next": "emit_tcp_fin"
    },
    {
      "name": "emit_tcp_fin",
      "type": "activity",
      "variables": [
        {"name": "var_end", "type": "clock"},
        {"name": "var_packets", "type": "constant", "value": 2},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 120, "max": 180}}
      ],
      "emitter": "tcp_flow",
      "next": "end"
    },
    {
      "name": "setup_tcp_rst",
      "type": "activity",
      "variables": [
        {"name": "var_start", "type": "clock"}
      ],
      "next": "timer_tcp_rst"
    },
    {
      "name": "timer_tcp_rst",
      "type": "event:intermediate:timer",
      "cardinality_distribution": {"type": "exponential", "mean": 0.05},
      "next": "emit_tcp_rst"
    },
    {
      "name": "emit_tcp_rst",
      "type": "activity",
      "variables": [
        {"name": "var_end", "type": "clock"},
        {"name": "var_packets", "type": "constant", "value": 1},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 54, "max": 66}}
      ],
      "emitter": "tcp_flow",
      "next": "end"
    },
    {
      "name": "end",
      "type": "event:end"
    }
  ]
}
```

### Packet and Byte Characteristics

#### SYN (Handshake)

- **Packets**: 3 (SYN, SYN-ACK, ACK)
- **Bytes**: 180-240 (60-80 bytes per packet including headers)
- **Duration**: Very short (~0.1 seconds)

#### Data Transfer

- **Packets**: Variable (50-500+ depending on payload size)
- **Bytes**: Variable (5KB-500KB+ depending on content)
- **Duration**: Variable (seconds to minutes)
- **May Continue**: 50% chance for additional data records

#### FIN (Graceful Close)

- **Packets**: 2 (FIN, ACK or FIN-ACK, ACK)
- **Bytes**: 120-180 (60-90 bytes per packet)
- **Duration**: Very short (~0.1 seconds)

#### RST (Connection Reset)

- **Packets**: 1 (RST)
- **Bytes**: 54-66 (single packet with headers)
- **Duration**: Very short (~0.05 seconds)
- **When**: Connection refused, timeout, or error (5% of connections)

### Real-World Example: VPC Flow Logs with TCP Lifecycle

The VPC Flow Logs configuration uses the setup+timer+emit pattern for each TCP phase:

```json
{
  "name": "setup_web_syn",
  "type": "activity",
  "variables": [
    {"name": "var_start", "type": "clock"}
  ],
  "next": "timer_web_syn"
},
{
  "name": "timer_web_syn",
  "type": "event:intermediate:timer",
  "cardinality_distribution": {"type": "uniform", "min": 1.0, "max": 2.0},
  "next": "emit_web_syn"
},
{
  "name": "emit_web_syn",
  "type": "activity",
  "variables": [
    {"name": "var_end", "type": "clock"},
    {"name": "var_packets", "type": "constant", "value": 3},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 180, "max": 240}}
  ],
  "emitter": "vpc_flow_log",
  "next": "setup_web_data"
},
{
  "name": "setup_web_data",
  "type": "activity",
  "variables": [
    {"name": "var_start", "type": "clock"}
  ],
  "next": "timer_web_data"
},
{
  "name": "timer_web_data",
  "type": "event:intermediate:timer",
  "cardinality_distribution": {"type": "uniform", "min": 5.0, "max": 30.0},
  "next": "emit_web_data"
},
{
  "name": "emit_web_data",
  "type": "activity",
  "variables": [
    {"name": "var_end", "type": "clock"},
    {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 50, "max": 500}},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 5000, "max": 500000}}
  ],
  "emitter": "vpc_flow_log",
  "next": "route_web_data"
},
{
  "name": "route_web_data",
  "type": "gateway:exclusive",
  "transitions": [
    {"next": "setup_web_fin", "probability": 0.5},
    {"next": "setup_web_data", "probability": 0.5}
  ]
},
{
  "name": "setup_web_fin",
  "type": "activity",
  "variables": [
    {"name": "var_start", "type": "clock"}
  ],
  "next": "timer_web_fin"
},
{
  "name": "timer_web_fin",
  "type": "event:intermediate:timer",
  "cardinality_distribution": {"type": "uniform", "min": 1.0, "max": 2.0},
  "next": "emit_web_fin"
},
{
  "name": "emit_web_fin",
  "type": "activity",
  "variables": [
    {"name": "var_end", "type": "clock"},
    {"name": "var_packets", "type": "constant", "value": 2},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 120, "max": 180}}
  ],
  "emitter": "vpc_flow_log",
  "next": "end"
}
```

**Result**:

- Same connection (5-tuple) appears in 2-4+ flow records
- First record: 3 packets, ~200 bytes, 1-2 second duration (SYN)
- Middle records: 50-500 packets, 5KB-500KB, 5-30 second duration (Data)
- Last record: 2 packets, ~150 bytes, 1-2 second duration (FIN)
- **Each phase uses the setup+timer+emit pattern for realistic flow duration**

### VPC Flow Log Use Cases

✅ **Security Analysis**: Detect SYN floods, port scans, incomplete handshakes
✅ **Capacity Planning**: Model realistic bandwidth consumption patterns
✅ **Anomaly Detection**: Identify connections with unusual packet/byte ratios
✅ **Protocol Testing**: Verify flow aggregation logic handles TCP states correctly

### VPC Flow Log Benefits

✅ **Protocol Realism**: Models actual TCP behavior
✅ **Security Testing**: Data suitable for IDS/IPS testing
✅ **Performance Analysis**: Realistic traffic patterns for load testing
✅ **Temporal Patterns**: Captures connection lifecycle timing

## Testing with Synthetic Clock

### Synthetic Clock Overview

**Critical Best Practice:** When developing configurations, ALWAYS use the synthetic clock (`-s`) for instant feedback. Only use real-time mode (`-t`) for production streaming scenarios.

The synthetic clock is one of the most important but often overlooked features for efficient development.

### The Clock Problem

Without synthetic clock, the generator honors real-time delays:

- Delay of 5 seconds → waits 5 seconds
- Delay of 60 seconds → waits 60 seconds
- Generating 1000 events with exponential delay (mean 10s) → **waits ~3 hours**

This makes development painfully slow.

### The Synthetic Clock Solution

The synthetic clock simulates time advancement without real waiting:

- Delay of 5 seconds → instant
- Delay of 60 seconds → instant
- Generating 1000 events with any delay → **completes in milliseconds**

### Usage

```bash
# BAD: Real-time mode (slow, waits for actual delays)
python3 generator.py -c vpc_flow_logs.json -n 1000

# GOOD: Synthetic clock (instant, perfect for development)
python3 generator.py -c vpc_flow_logs.json -n 1000 -s "2024-01-01T00:00:00"

# GOOD: With output file
python3 generator.py -c vpc_flow_logs.json -n 1000 -s "2024-01-01T00:00:00" > flows.json
```

### How Synthetic Clock Works

1. **Start Time**: Clock initialized to specified time (e.g., `2024-01-01T00:00:00`)
2. **Delay Processing**: When state has delay of 5 seconds, clock advances by 5 seconds instantly
3. **Clock Variables**: `var_start` and `var_end` use synthetic clock values
4. **Result**: All 1000 events generated in milliseconds with realistic timestamps

### Example Synthetic Clock Output

With synthetic clock starting at `2024-01-01T00:00:00`:

```json
{"start": 1704067200, "end": 1704067205, "packets": 3, "bytes": 215}
{"start": 1704067205, "end": 1704067210, "packets": 150, "bytes": 125000}
{"start": 1704067210, "end": 1704067211, "packets": 2, "bytes": 145}
```

**Notice**: Realistic timestamps with proper delays between records, generated instantly.

### When to Use Real-Time Mode

Use real-time mode (`-t`) only for:

- **Production streaming**: Sending events to Kafka, Kinesis, etc. at realistic rates
- **Load testing**: Simulating realistic request rates
- **Live demos**: Showing real-time data generation

```bash
# Real-time mode (events generated at realistic intervals)
python3 generator.py -c vpc_flow_logs.json -t "2024-01-01T00:00:00"
```

### Development Workflow

```bash
# 1. Quick validation (synthetic clock, small dataset)
python3 generator.py -c vpc_flow_logs.json -n 100 -s "2024-01-01T00:00:00" > test.json

# 2. Inspect output
head -20 test.json
jq '.packets' test.json | sort -n | uniq -c  # Check packet distribution

# 3. Generate larger dataset (still instant with synthetic clock)
python3 generator.py -c vpc_flow_logs.json -n 10000 -s "2024-01-01T00:00:00" > large_test.json

# 4. Analyze patterns
jq -r '[.start, .end, (.end - .start)] | @csv' large_test.json > durations.csv

# 5. Once validated, use real-time mode for production
python3 generator.py -c vpc_flow_logs.json -t "2024-01-01T00:00:00" | kafka-producer ...
```

### Synthetic Clock Benefits

✅ **Instant Feedback**: Milliseconds instead of minutes/hours
✅ **Rapid Iteration**: Test changes immediately
✅ **Large Datasets**: Generate 100K+ events in seconds
✅ **Deterministic Testing**: Same start time = reproducible output
✅ **Time Travel**: Test historical time ranges instantly

### Common Mistakes

❌ **Not using synthetic clock during development**

```bash
# This will take HOURS with realistic delays
python3 generator.py -c vpc_flow_logs.json -n 10000
```

❌ **Forgetting -s parameter**

```bash
# Missing -s means real-time mode (slow)
python3 generator.py -c vpc_flow_logs.json -n 10000 "2024-01-01T00:00:00"
```

✅ **Always use -s during development**

```bash
# Instant generation
python3 generator.py -c vpc_flow_logs.json -n 10000 -s "2024-01-01T00:00:00"
```

## Summary

These six patterns represent essential techniques for building realistic, efficient state machine configurations:

1. **Variable Persistence**: Variables persist across states - only redefine what changes
2. **Flow Duration with Setup and Timer States**: Use a `setup_*` activity to capture start time, an `event:intermediate:timer` for the delay, and an `emit_*` activity to capture end time and emit the record
3. **Common Variables in Initial State**: Move shared variables to initial state for efficiency and realism
4. **Multiple Records Per Connection**: Use continue loops for long-running connections
5. **TCP Lifecycle**: Model protocol phases with realistic packet/byte characteristics
6. **Synthetic Clock**: Use `-s` flag for instant development feedback
