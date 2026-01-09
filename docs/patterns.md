# Common State Machine Patterns

This guide documents common patterns and techniques for building realistic state machine configurations. These patterns were discovered while creating production-quality synthetic data generators and represent best practices for achieving realistic, efficient configurations.

## Table of Contents

1. [Variable Persistence Across States](#variable-persistence-across-states)
2. [Start→Activity→Emit Pattern (Flow Duration)](#startactivityemit-pattern-flow-duration)
3. [Common Variables in Initial State](#common-variables-in-initial-state)
4. [Multiple Records Per Connection](#multiple-records-per-connection)
5. [TCP Connection Lifecycle Pattern](#tcp-connection-lifecycle-pattern)
6. [Testing with Synthetic Clock](#testing-with-synthetic-clock)

## Variable Persistence Across States

### Overview

**Key Insight:** Variables set in one state automatically persist to all subsequent states within the same worker thread. You only need to redefine variables that change.

This is one of the most important concepts for building efficient state machines. Understanding variable persistence allows you to:

- Avoid unnecessary variable redefinitions
- Build complex state machines without repetition
- Create cleaner, more maintainable configurations

### The Pattern

```json
{
  "states": [
    {
      "name": "connection_start",
      "variables": [
        {"name": "user_id", "type": "string", "distribution": {"type": "uniform", "min": 1000, "max": 9999}},
        {"name": "session_id", "type": "string", "distribution": {"type": "uniform", "min": 100000, "max": 999999}}
      ],
      "transitions": [{"next": "page_view", "probability": 1.0}]
    },
    {
      "name": "page_view",
      "emitter": "web_event",
      "variables": [
        {"name": "page_name", "type": "enum", "values": ["home", "products", "checkout"]}
        // user_id and session_id automatically available here!
      ],
      "transitions": [{"next": "page_view", "probability": 0.7}]
    }
  ]
}
```

### How It Works

1. **First State** (connection_start): Defines `user_id` and `session_id`
2. **Subsequent States** (page_view): Can reference `user_id` and `session_id` without redefining them
3. **Worker Scope**: Variables persist for the lifetime of the worker thread
4. **Only Redefine What Changes**: Only define new variables or variables whose values should change

### Common Use Cases

- **Connection-level attributes**: IP addresses, user IDs, session IDs
- **Transaction attributes**: Order IDs, customer information
- **Flow attributes**: Source/destination addresses, ports

### Example: VPC Flow Logs

```json
{
  "states": [
    {
      "name": "initial",
      "variables": [
        {"name": "var_account_id", "type": "enum", "values": ["123456789012", "123456789013"]},
        {"name": "var_interface_id", "type": "enum", "values": ["eni-1a2b3c4d", "eni-5e6f7g8h"]},
        {"name": "var_action", "type": "enum", "values": ["ACCEPT", "REJECT"], "probabilities": [0.95, 0.05]}
      ],
      "transitions": [
        {"next": "web_traffic_setup", "probability": 0.4},
        {"next": "api_traffic_setup", "probability": 0.6}
      ]
    },
    {
      "name": "web_traffic_setup",
      "variables": [
        {"name": "var_srcaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "10.0.0.0/16"}},
        {"name": "var_dstaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "203.0.113.0/24"}},
        {"name": "var_srcport", "type": "int", "distribution": {"type": "uniform", "min": 1024, "max": 65535}},
        {"name": "var_dstport", "type": "constant", "value": 443}
        // var_account_id, var_interface_id, var_action all available here!
      ],
      "transitions": [{"next": "web_traffic_emit", "probability": 1.0}]
    }
  ]
}
```

### Benefits

✅ **Reduced Configuration Size**: 20-30% smaller configs for complex state machines
✅ **Easier Maintenance**: Change common variables in one place
✅ **Better Performance**: Fewer variable computations per state
✅ **Clearer Intent**: Shows which variables are connection-wide vs state-specific

## Start→Activity→Emit Pattern (Flow Duration)

### Flow Overview

**Problem:** When modeling events with duration (network flows, sessions, transactions), naively capturing both start and end times in the same state results in instantaneous events where `start == end`.

**Solution:** Use a three-state pattern that separates setup, delay, and emission to create realistic time windows.

This is the **most important pattern for time-windowed data** like network flows, session logs, or transaction records.

### Flow Pattern

```text
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ Setup State  │        │ Activity     │        │ Emit State   │
│ (no emitter) │───────▶│ State        │───────▶│ (emitter)    │
│              │        │ (no emitter) │        │              │
│ - Capture    │        │ - Delay for  │        │ - Capture    │
│   start time │        │   duration   │        │   end time   │
│ - Setup vars │        │ - No emit    │        │ - Calculate  │
│ - No emit    │        │              │        │   metrics    │
│              │        │              │        │ - Emit record│
└──────────────┘        └──────────────┘        └──────────────┘
```

### Configuration Example

```json
{
  "states": [
    {
      "name": "flow_start",
      "comment": "State 1: Capture start time and connection details (no emitter)",
      "variables": [
        {"name": "var_start", "type": "clock"},
        {"name": "var_srcaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "10.0.0.0/16"}},
        {"name": "var_dstaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "203.0.113.0/24"}},
        {"name": "var_srcport", "type": "int", "distribution": {"type": "uniform", "min": 1024, "max": 65535}},
        {"name": "var_dstport", "type": "constant", "value": 443}
      ],
      "delay": {"type": "constant", "value": 0},
      "transitions": [{"next": "flow_activity", "probability": 1.0}]
    },
    {
      "name": "flow_activity",
      "comment": "State 2: Delay for the flow duration (no emitter, no variables)",
      "variables": [],
      "delay": {"type": "exponential", "mean": 5.0},
      "transitions": [{"next": "flow_emit", "probability": 1.0}]
    },
    {
      "name": "flow_emit",
      "comment": "State 3: Capture end time, calculate metrics, emit record",
      "emitter": "flow_record",
      "variables": [
        {"name": "var_end", "type": "clock"},
        {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 10, "max": 1000}},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 1000, "max": 1000000}}
      ],
      "delay": {"type": "constant", "value": 0},
      "transitions": [{"next": "flow_start", "probability": 0.3}]
    }
  ]
}
```

### Why This Works

1. **State 1** (flow_start): Captures `var_start` using clock at time T₀
2. **State 2** (flow_activity): Simulation advances time by delay (e.g., 5 seconds)
3. **State 3** (flow_emit): Captures `var_end` using clock at time T₀ + 5 seconds
4. **Result**: Emitted record has `start < end` with realistic duration

### Without This Pattern (Anti-Pattern)

```json
{
  "name": "flow_bad",
  "emitter": "flow_record",
  "variables": [
    {"name": "var_start", "type": "clock"},
    {"name": "var_end", "type": "clock"}
    // Both sampled at same instant! start == end (unrealistic)
  ]
}
```

**Problem**: Both `var_start` and `var_end` are sampled at the same instant, resulting in zero-duration flows.

### Use Cases

- **Network flow logs** (VPC Flow Logs, NetFlow, sFlow)
- **Session logs** (web sessions, API sessions)
- **Transaction logs** (database transactions, API transactions)
- **Call detail records** (phone calls, video conferences)
- **Any event with a meaningful duration**

### Variations

#### Multiple Activity States

For complex lifecycles (e.g., TCP handshake, data transfer, teardown):

```json
{
  "states": [
    {"name": "tcp_setup", "variables": [{"name": "var_start", "type": "clock"}], "transitions": [{"next": "tcp_syn_delay", "probability": 1.0}]},
    {"name": "tcp_syn_delay", "delay": {"type": "exponential", "mean": 0.1}, "transitions": [{"next": "tcp_syn_emit", "probability": 1.0}]},
    {"name": "tcp_syn_emit", "emitter": "tcp_flow", "variables": [{"name": "var_end", "type": "clock"}, {"name": "var_packets", "type": "constant", "value": 3}]},

    {"name": "tcp_data_delay", "delay": {"type": "exponential", "mean": 5.0}, "transitions": [{"next": "tcp_data_emit", "probability": 1.0}]},
    {"name": "tcp_data_emit", "emitter": "tcp_flow", "variables": [{"name": "var_end", "type": "clock"}, {"name": "var_packets", "distribution": {"type": "uniform", "min": 50, "max": 500}}]}
  ]
}
```

### Flow Benefits

✅ **Realistic Time Windows**: Events have proper duration (start < end)
✅ **Accurate Metrics**: Can model throughput, packets/bytes over time
✅ **Protocol Accuracy**: Models real-world connection lifecycles
✅ **Testable**: Easy to verify duration ranges in generated data

---

## Common Variables in Initial State

### Initial State Overview

**Optimization:** Move variables that are common across all execution paths to the initial routing state. This reduces configuration size and makes intent clearer.

This pattern builds on [Variable Persistence](#variable-persistence-across-states) to optimize large state machines with multiple traffic patterns.

### Initial State Pattern

#### Before Optimization

```json
{
  "states": [
    {
      "name": "initial",
      "transitions": [
        {"next": "web_traffic", "probability": 0.4},
        {"next": "api_traffic", "probability": 0.6}
      ]
    },
    {
      "name": "web_traffic",
      "emitter": "access_log",
      "variables": [
        {"name": "account_id", "type": "enum", "values": ["account-1", "account-2"]},
        {"name": "region", "type": "enum", "values": ["us-east-1", "us-west-2"]},
        {"name": "url", "type": "enum", "values": ["/home", "/products"]}
      ]
    },
    {
      "name": "api_traffic",
      "emitter": "api_log",
      "variables": [
        {"name": "account_id", "type": "enum", "values": ["account-1", "account-2"]},
        {"name": "region", "type": "enum", "values": ["us-east-1", "us-west-2"]},
        {"name": "endpoint", "type": "enum", "values": ["/api/v1/users", "/api/v1/orders"]}
      ]
    }
  ]
}
```

**Problem**: `account_id` and `region` are duplicated in both states.

#### After Optimization

```json
{
  "states": [
    {
      "name": "initial",
      "variables": [
        {"name": "account_id", "type": "enum", "values": ["account-1", "account-2"]},
        {"name": "region", "type": "enum", "values": ["us-east-1", "us-west-2"]}
      ],
      "transitions": [
        {"next": "web_traffic", "probability": 0.4},
        {"next": "api_traffic", "probability": 0.6}
      ]
    },
    {
      "name": "web_traffic",
      "emitter": "access_log",
      "variables": [
        {"name": "url", "type": "enum", "values": ["/home", "/products"]}
      ]
    },
    {
      "name": "api_traffic",
      "emitter": "api_log",
      "variables": [
        {"name": "endpoint", "type": "enum", "values": ["/api/v1/users", "/api/v1/orders"]}
      ]
    }
  ]
}
```

**Benefit**: Eliminated 4 lines of duplicate variable definitions.

### Real-World Example: VPC Flow Logs

The VPC Flow Logs configuration has multiple traffic patterns (web, API, database, DNS, SSH, rejected traffic, port scans). Variables common to **all** flows were moved to the initial state:

```json
{
  "name": "initial",
  "variables": [
    {
      "name": "var_account_id",
      "type": "enum",
      "values": ["123456789012", "123456789013", "123456789014"],
      "probabilities": [0.5, 0.3, 0.2]
    },
    {
      "name": "var_interface_id",
      "type": "enum",
      "values": [
        "eni-1a2b3c4d", "eni-5e6f7g8h", "eni-9i0j1k2l", "eni-3m4n5o6p",
        "eni-7q8r9s0t", "eni-1u2v3w4x", "eni-5y6z7a8b", "eni-9c0d1e2f"
      ]
    },
    {
      "name": "var_action",
      "type": "enum",
      "values": ["ACCEPT", "REJECT"],
      "probabilities": [0.95, 0.05]
    }
  ],
  "transitions": [
    {"next": "web_traffic_connection_setup", "probability": 0.35},
    {"next": "api_traffic_connection_setup", "probability": 0.25},
    {"next": "database_traffic_connection_setup", "probability": 0.15},
    {"next": "dns_query_setup", "probability": 0.10},
    {"next": "ssh_traffic_connection_setup", "probability": 0.05},
    {"next": "rejected_traffic_setup", "probability": 0.05},
    {"next": "port_scan_setup", "probability": 0.05}
  ]
}
```

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

---

## Multiple Records Per Connection

### Multi-record Overview

Real-world connections often generate multiple observation records over time. Examples:

- **VPC Flow Logs**: Multiple 60-second aggregation windows for the same connection
- **Session Logs**: Multiple events (pageviews, clicks) for the same session
- **Transaction Logs**: Multiple line items for the same order

**Pattern:** Use a continue/loop state to emit multiple records for the same connection.

### Multi-record Pattern

```text
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ Emit Record  │───70%─▶│ Close        │        │              │
│              │        │ Connection   │        │              │
│              │        │              │        │              │
│              │───30%─▶│ Continue     │───────▶│ Activity     │─┐
│              │        │ Connection   │        │ State        │ │
│              │◀───────┴──────────────┴────────┴──────────────┘ │
└──────────────┘                                                 │
       ▲                                                          │
       └──────────────────────────────────────────────────────────┘
```

### Multi-record Configuration Example

```json
{
  "states": [
    {
      "name": "connection_setup",
      "comment": "Initial connection setup",
      "variables": [
        {"name": "var_srcaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "10.0.0.0/16"}},
        {"name": "var_dstaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "203.0.113.0/24"}},
        {"name": "var_srcport", "type": "int", "distribution": {"type": "uniform", "min": 1024, "max": 65535}},
        {"name": "var_dstport", "type": "constant", "value": 443}
      ],
      "transitions": [{"next": "flow_activity", "probability": 1.0}]
    },
    {
      "name": "flow_activity",
      "delay": {"type": "exponential", "mean": 60.0},
      "transitions": [{"next": "emit_flow_record", "probability": 1.0}]
    },
    {
      "name": "emit_flow_record",
      "emitter": "flow_log",
      "variables": [
        {"name": "var_start", "type": "clock"},
        {"name": "var_end", "type": "clock"},
        {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 100, "max": 10000}},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 10000, "max": 1000000}}
      ],
      "transitions": [
        {"next": "close_flow", "probability": 0.7},
        {"next": "continue_flow", "probability": 0.3}
      ]
    },
    {
      "name": "continue_flow",
      "comment": "Continue same connection - emit another record after delay",
      "variables": [],
      "delay": {"type": "constant", "value": 0},
      "transitions": [{"next": "flow_activity", "probability": 1.0}]
    },
    {
      "name": "close_flow",
      "comment": "Connection closed",
      "variables": [],
      "delay": {"type": "constant", "value": 0},
      "transitions": []
    }
  ]
}
```

### How Multi-record Works

1. **First Emission**: Connection emits first flow record after initial activity
2. **Decision Point**: 30% chance to continue, 70% chance to close
3. **Continue Path**: Loops back to activity state (delay) → emit another record
4. **Same Connection**: Source/destination IPs and ports persist across all records
5. **Result**: Same 5-tuple appears in multiple flow records with different time windows

### Real-World Multi-record Example: VPC Flow Logs

```json
{
  "name": "web_traffic_data_emit",
  "emitter": "vpc_flow_log",
  "variables": [
    {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 50, "max": 500}},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 5000, "max": 500000}},
    {"name": "var_end", "type": "clock"}
  ],
  "delay": {"type": "constant", "value": 0},
  "transitions": [
    {"next": "web_traffic_fin_setup", "probability": 0.5},
    {"next": "web_traffic_continue", "probability": 0.5}
  ]
},
{
  "name": "web_traffic_continue",
  "comment": "Continue connection - emit another data record",
  "variables": [
    {"name": "var_start", "type": "clock"}
  ],
  "delay": {"type": "constant", "value": 0},
  "transitions": [{"next": "web_traffic_data_activity", "probability": 1.0}]
}
```

### Multi-record Variations

#### Increasing Probability of Closure

Make long-running connections less likely:

```json
{
  "transitions": [
    {"next": "close", "probability": 0.5},
    {"next": "continue_once", "probability": 0.5}
  ]
}
// ...
{
  "name": "emit_record_2",
  "transitions": [
    {"next": "close", "probability": 0.7},
    {"next": "continue_twice", "probability": 0.3}
  ]
}
// ...
{
  "name": "emit_record_3",
  "transitions": [
    {"next": "close", "probability": 0.9},
    {"next": "continue_thrice", "probability": 0.1}
  ]
}
```

**Result**: Most connections emit 1-2 records, fewer emit 3+, very few emit 4+.

#### Session Events (Multiple Event Types)

```json
{
  "name": "emit_pageview",
  "emitter": "session_event",
  "variables": [
    {"name": "event_type", "type": "constant", "value": "pageview"},
    {"name": "page_url", "type": "enum", "values": ["/home", "/products", "/checkout"]}
  ],
  "transitions": [
    {"next": "session_end", "probability": 0.2},
    {"next": "emit_click", "probability": 0.5},
    {"next": "emit_pageview", "probability": 0.3}
  ]
},
{
  "name": "emit_click",
  "emitter": "session_event",
  "variables": [
    {"name": "event_type", "type": "constant", "value": "click"},
    {"name": "button_id", "type": "enum", "values": ["add_to_cart", "buy_now", "learn_more"]}
  ],
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

---

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

```json
{
  "states": [
    {
      "name": "tcp_connection_setup",
      "comment": "Setup connection 5-tuple",
      "variables": [
        {"name": "var_srcaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "10.0.0.0/16"}},
        {"name": "var_dstaddr", "type": "ipaddress", "distribution": {"type": "cidr", "value": "203.0.113.0/24"}},
        {"name": "var_srcport", "type": "int", "distribution": {"type": "uniform", "min": 1024, "max": 65535}},
        {"name": "var_dstport", "type": "constant", "value": 443},
        {"name": "var_start", "type": "clock"}
      ],
      "transitions": [{"next": "tcp_syn_activity", "probability": 1.0}]
    },
    {
      "name": "tcp_syn_activity",
      "delay": {"type": "exponential", "mean": 0.1},
      "transitions": [{"next": "tcp_syn_emit", "probability": 1.0}]
    },
    {
      "name": "tcp_syn_emit",
      "emitter": "tcp_flow",
      "comment": "TCP handshake: 3 packets (SYN, SYN-ACK, ACK)",
      "variables": [
        {"name": "var_packets", "type": "constant", "value": 3},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 180, "max": 240}},
        {"name": "var_end", "type": "clock"}
      ],
      "transitions": [
        {"next": "tcp_data_activity", "probability": 0.95},
        {"next": "tcp_rst_activity", "probability": 0.05}
      ]
    },
    {
      "name": "tcp_data_activity",
      "delay": {"type": "exponential", "mean": 5.0},
      "transitions": [{"next": "tcp_data_emit", "probability": 1.0}]
    },
    {
      "name": "tcp_data_emit",
      "emitter": "tcp_flow",
      "comment": "Data transfer: variable packets/bytes",
      "variables": [
        {"name": "var_start", "type": "clock"},
        {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 50, "max": 500}},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 5000, "max": 500000}},
        {"name": "var_end", "type": "clock"}
      ],
      "transitions": [
        {"next": "tcp_fin_activity", "probability": 0.5},
        {"next": "tcp_data_continue", "probability": 0.5}
      ]
    },
    {
      "name": "tcp_data_continue",
      "comment": "Continue data transfer",
      "transitions": [{"next": "tcp_data_activity", "probability": 1.0}]
    },
    {
      "name": "tcp_fin_activity",
      "delay": {"type": "exponential", "mean": 0.1},
      "transitions": [{"next": "tcp_fin_emit", "probability": 1.0}]
    },
    {
      "name": "tcp_fin_emit",
      "emitter": "tcp_flow",
      "comment": "Graceful close: 2 packets (FIN, ACK)",
      "variables": [
        {"name": "var_start", "type": "clock"},
        {"name": "var_packets", "type": "constant", "value": 2},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 120, "max": 180}},
        {"name": "var_end", "type": "clock"}
      ],
      "transitions": []
    },
    {
      "name": "tcp_rst_activity",
      "delay": {"type": "exponential", "mean": 0.05},
      "transitions": [{"next": "tcp_rst_emit", "probability": 1.0}]
    },
    {
      "name": "tcp_rst_emit",
      "emitter": "tcp_flow",
      "comment": "Connection reset: 1 packet (RST)",
      "variables": [
        {"name": "var_start", "type": "clock"},
        {"name": "var_packets", "type": "constant", "value": 1},
        {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 54, "max": 66}},
        {"name": "var_end", "type": "clock"}
      ],
      "transitions": []
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

From the VPC Flow Logs configuration:

```json
{
  "name": "web_traffic_syn_emit",
  "emitter": "vpc_flow_log",
  "variables": [
    {"name": "var_packets", "type": "constant", "value": 3},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 180, "max": 240}},
    {"name": "var_end", "type": "clock"}
  ],
  "transitions": [
    {"next": "web_traffic_data_setup", "probability": 1.0}
  ]
},
{
  "name": "web_traffic_data_emit",
  "emitter": "vpc_flow_log",
  "variables": [
    {"name": "var_packets", "type": "int", "distribution": {"type": "uniform", "min": 50, "max": 500}},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 5000, "max": 500000}},
    {"name": "var_end", "type": "clock"}
  ],
  "transitions": [
    {"next": "web_traffic_fin_setup", "probability": 0.5},
    {"next": "web_traffic_continue", "probability": 0.5}
  ]
},
{
  "name": "web_traffic_fin_emit",
  "emitter": "vpc_flow_log",
  "variables": [
    {"name": "var_packets", "type": "constant", "value": 2},
    {"name": "var_bytes", "type": "int", "distribution": {"type": "uniform", "min": 120, "max": 180}},
    {"name": "var_end", "type": "clock"}
  ],
  "transitions": []
}
```

**Result**:

- Same connection (5-tuple) appears in 2-4+ flow records
- First record: 3 packets, ~200 bytes (SYN)
- Middle records: 50-500 packets, 5KB-500KB (Data)
- Last record: 2 packets, ~150 bytes (FIN)

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

---

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

---

## Summary

These six patterns represent essential techniques for building realistic, efficient state machine configurations:

1. **Variable Persistence**: Variables persist across states - only redefine what changes
2. **Start→Activity→Emit**: Three-state pattern for realistic flow duration
3. **Common Variables**: Move shared variables to initial state for efficiency
4. **Multiple Records**: Use continue loops for long-running connections
5. **TCP Lifecycle**: Model protocol phases with realistic packet/byte characteristics
6. **Synthetic Clock**: Use `-s` flag for instant development feedback

**Key Takeaways:**

- Understand variable persistence to avoid duplication
- Use Start→Activity→Emit for any time-windowed data
- Optimize large configs by moving common variables up
- Model realistic connection lifecycles with multiple records and protocol phases
- Always develop with synthetic clock, only use real-time for production

For more information, see:

- [Generator Specification](genspec.md) - Core concepts and field reference
- [States Documentation](genspec-states.md) - Detailed state configuration guide
- [Best Practices](best-practices.md) - Configuration guidelines and conventions

---

*These patterns were discovered during the development of production-quality VPC Flow Logs synthetic data generation. They represent battle-tested approaches for creating realistic, performant state machine configurations.*
