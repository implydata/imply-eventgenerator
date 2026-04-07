# PBX Calls

Simulates Asterisk IP PBX call detail records (`asterisk_cdr` sourcetype). Models the full call lifecycle from dialling through to completion, with realistic outcomes and durations.

**Actor:** A caller making a phone call. Each worker represents one person picking up the phone, waiting for an answer, and either completing the call or hanging up.

## Quick start

```bash
python generator.py -c presets/configs/pbx_calls.json --template asterisk_cdr -n 100 -s "2025-01-01T00:00"

# One hour of data
python generator.py -c presets/configs/pbx_calls.json --template asterisk_cdr -r PT1H -s "2025-01-01T00:00"

# Concurrent callers
python generator.py -c presets/configs/pbx_calls.json --template asterisk_cdr -r PT1H -s "2025-01-01T00:00" -m 5
```

## Template

| Template | Output |
| --- | --- |
| `asterisk_cdr` | Asterisk CDR CSV format |

## Output fields

| Field | Description |
| --- | --- |
| `accountcode` | Account code (`sales`, `support`, `billing`, or empty) |
| `src` | Caller phone number (10-digit) |
| `dst` | Destination extension (4-digit) |
| `clid` | Caller ID (same as `src`) |
| `channel` | Originating SIP channel |
| `dstchannel` | Destination SIP channel (empty if unanswered) |
| `lastapp` | Last Asterisk application executed (`Dial`) |
| `lastdata` | Arguments to `lastapp` |
| `start` | Call start timestamp |
| `answer` | Answer timestamp (same as `start`) |
| `end` | Call end timestamp (same as `start`) |
| `duration` | Total call duration in seconds |
| `billsec` | Billable seconds (`duration` for ANSWERED, `0` otherwise) |
| `disposition` | Call outcome: `ANSWERED`, `NO ANSWER`, or `BUSY` |
| `amaflags` | AMA flags (always `DOCUMENTATION`) |

> `start`, `answer`, and `end` all carry the same clock timestamp since the generator emits the CDR as a single event at call completion. Use `duration` and `billsec` for time-range analysis.

## State machine

```text
[start] ──→ initial ──→ ringing (5–30 s)
                              ↓
                   ┌──────────┼────────────┐
                  70%        20%          10%
                   ↓          ↓            ↓
               answered   no_answer      busy
             (~180 s talk)  (emit CDR)  (emit CDR)
                   ↓            ↓            ↓
               (emit CDR)     stop         stop
                   ↓
                  stop
```

The `ringing` state models real ring time (5–30 s) before the outcome is determined. Answered calls spend an additional ~3 minutes in `answered` before the CDR is emitted — so in real-time mode, `-m` controls how many calls are genuinely in progress simultaneously.

## Concurrency (`-m`)

| Little's Law component | Value |
| --- | --- |
| Average session duration (W) | ~144 seconds |
| Interarrival mean | 30 s |
| Base arrival rate (λ = 1/mean) | ~0.033 calls/sec |
| Maximum useful `-m` (L = λW) | ~5 |

At the default interarrival rate, only ~5 calls are naturally in flight at any moment. To model a busier PBX, lower the `interarrival` mean in the config.
