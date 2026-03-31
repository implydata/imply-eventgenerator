# Ecommerce — Lighting Store

A high-traffic e-commerce scenario simulating a lighting retailer. Busier than the generic ecommerce config, with shorter average session durations due to faster product decisions in a commodity-adjacent category.

## Quick start

```bash
# Apache combined log
python generator.py -c presets/configs/ecommerce_lighting.json --template access_combined -n 100 -s "2025-01-01T00:00"

# JSON (Splunk TA)
python generator.py -c presets/configs/ecommerce_lighting.json --template apache:access:json -r PT1H -s "2025-01-01T00:00"

# CSV
python generator.py -c presets/configs/ecommerce_lighting.json --template csv -n 1000 -s "2025-01-01T00:00"

# With time-of-day variation
python generator.py -c presets/configs/ecommerce_lighting.json --template access_combined \
  -m 500 --schedule presets/schedules/ecommerce.json
```

## Templates

| Template | Output |
| --- | --- |
| `apache:access:json` | Splunk TA JSON (`KV_MODE=json`) |
| `apache:access:kv` | Splunk TA key=value pairs |
| `apache:access:combined` | NCSA combined log (Splunk `apache:access:combined` sourcetype) |
| `access_combined` | NCSA combined log (Splunk `access_combined` pre-trained sourcetype) |
| `access_combined_wcookie` | NCSA combined log with cookie field appended |
| `access_common` | NCSA common log (no referrer or user-agent) |
| `csv` | CSV with header row |

## Output fields

| Field | Description |
| --- | --- |
| `time` | Request timestamp |
| `client` | Client IP address |
| `ident` | RFC 1413 identity (always `-`) |
| `user` | Authenticated username (usually `-`) |
| `http_method` | HTTP method (`GET`, `POST`, etc.) |
| `uri_path` | Request path |
| `uri_query` | Query string (empty if none) |
| `http_version` | Protocol version (`HTTP/1.1`, `HTTP/2.0`) |
| `status` | HTTP response status code |
| `bytes_out` | Response bytes |
| `bytes_in` | Request bytes |
| `http_referrer` | Referrer URL |
| `http_user_agent` | User-Agent string |
| `http_content_type` | Content-Type of the response |
| `cookie` | Session cookie value |
| `server` | Server IP address |
| `dest_port` | Server port (80 or 443) |
| `response_time_microseconds` | Response latency in microseconds |

## Product categories

| Category | Weight | Example products |
| --- | --- | --- |
| Indoor | 40% | Aurora chandelier, nebula table lamp, stellar floor lamp, eclipse wall sconce |
| Outdoor | 20% | Solar path light, moonlit garden lamp, starlight wall lantern |
| Smart | 15% | Voice-controlled bulb, color-changing bulb, wifi LED strip |
| LED | 15% | Ultra bright LED bulb, eco-friendly LED panel, LED desk lamp |
| Vintage | 8% | Retro chandelier, antique wall lamp, industrial pendant light |

## State machine

Workers simulate a browsing session:

```text
           (98.9%)──→ browse_products ──→ browse_cat_* ⟲
[start] ──→(0.1%) ──→ hacker ⟲               ↓
           (1.0%) ──→ stop            add_to_cart
                          ↓                   ↓
                      not_found           checkout ──→ thank_you ──→ stop
                          ↓                   ↓
                      browse_products     try_again ──→ checkout
```

Each `browse_cat_*` state corresponds to a product category (Indoor, Outdoor, Smart, LED, Vintage). From a category state the worker can: self-loop (browse more in that category), proceed to `add_to_cart`, return to `browse_products`, or stop. `browse_products` itself also has a direct stop path. `not_found` is a dead-end 404 that loops back to `browse_products`.

Session-level properties (IP, user-agent, cookie, server) are drawn once at entry and persist for the full session. Page dwell times are drawn from uniform distributions (seconds to minutes, depending on category and config).

0.1% of sessions are "hacker" sessions: on entry the worker switches to rapid-fire exploit attempts (0.01 s interarrival, 404/403/400 responses, probing paths such as `/.env`, `/admin`, `/wp-login.php`). The hacker loop self-continues with 99% probability, averaging ~100 requests before stopping.

## Concurrency (`-m`)

| Little's Law component | Value |
| --- | --- |
| Average session duration (W) | ~819 seconds (~14 minutes) |
| Interarrival mean | 0.6 s |
| Base arrival rate (λ = 1/mean) | ~1.67 sessions/sec |
| Maximum useful `-m` (L = λW) | ~1,365 |

Setting `-m` above ~1,365 has no effect — sessions complete faster than new ones arrive to fill the pool.
