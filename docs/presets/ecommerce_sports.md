# Ecommerce — Sports Store

A high-traffic e-commerce scenario simulating a sports and outdoor equipment retailer. Similar traffic volume to the lighting store, with moderate dwell times reflecting active comparison shopping. Referrer traffic skews toward fitness and outdoor media (YouTube, Reddit, Strava, Runner's World, REI) rather than general shopping aggregators.

## Quick start

```bash
# Apache combined log
python generator.py -c presets/configs/ecommerce_sports.json --template access_combined -n 100 -s "2025-01-01T00:00"

# JSON (Splunk TA)
python generator.py -c presets/configs/ecommerce_sports.json --template apache:access:json -r PT1H -s "2025-01-01T00:00"

# CSV
python generator.py -c presets/configs/ecommerce_sports.json --template csv -n 1000 -s "2025-01-01T00:00"

# With time-of-day variation
python generator.py -c presets/configs/ecommerce_sports.json --template access_combined \
  -m 700 --schedule presets/schedules/ecommerce.json

# IIS W3C log (Splunk ms:iis:auto sourcetype — recommended)
python generator.py -c presets/configs/ecommerce_sports.json --template ms:iis:auto -r PT1H -s "2025-01-01T00:00"
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
| `ms:iis:auto` | IIS W3C log (`ms:iis:auto` sourcetype) |
| `ms:iis:default:85` | IIS W3C log (`ms:iis:default:85` sourcetype — identical output to `ms:iis:auto`, included for completeness) |
| `ms:iis:default` | IIS W3C log (`ms:iis:default` sourcetype, IIS 7.0 field ordering) |
| `ms:iis:splunk` | IIS W3C log (`ms:iis:splunk` sourcetype, adds `Content-Type` and `https` fields) |
| `ocsf:http_activity` | [OCSF](https://schema.ocsf.io/) 1.4.0 HTTP Activity (`class_uid` 4002) JSON — one event per request, for security data lake / SIEM ingestion |

When generating IIS data for Splunk, use `--template ms:iis:auto` — the other IIS templates are included for completeness but have been marked as deprecated by Splunk.

The `ocsf:http_activity` template maps every session's requests — human, bot, and the `Hacker` actor's probe traffic — onto the OCSF Network Activity category. `activity_id`/`type_uid` are derived from `http_method`; `severity_id`/`status_id` are derived from `status` (2xx/3xx → informational/success, 4xx → medium/failure, 5xx → high/failure). Verified against the real OCSF 1.4.0 `http_activity` JSON Schema (via the [`ocsf-json-schema`](https://github.com/nsmithuk/ocsf-json-schema) package) across all three actor types.

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
| `server` | Server IP address (`10.0.4.x`) |
| `dest_port` | Server port (80, 443, or 8080) |
| `response_time_microseconds` | Response latency in microseconds |

## Product categories

| Category | Weight | Example products |
| --- | --- | --- |
| Fitness & gym | 32% | Adjustable dumbbell set, resistance bands, yoga mat, kettlebell, foam roller |
| Outdoor & hiking | 23% | Trail running vest, ultralight sleeping bag, trekking poles, headlamp, tent |
| Team sports | 17% | Match football, cricket bat, basketball, rugby ball, hockey stick, goalkeeper gloves |
| Cycling | 14% | Road bike helmet, cycling gloves, LED bike lights, GPS cycling computer, clip pedals |
| Water sports | 9% | Swim cap, triathlon wetsuit, open-water goggles, paddle board, kayak paddle |

## Session routing

Each session is routed at startup by `global_init` (no event emitted):

| Session type | Probability | Description |
| --- | --- | --- |
| Human | 99.5% | Normal shopper browsing the store |
| Hacker | 0.1% | Automated scanner probing for vulnerabilities |
| Bot | 0.4% | Web crawler indexing site content |

```mermaid
flowchart LR
    A(["<b>session_start</b><br/>event:start:timer"]) --> B["<b>global_init</b><br/>activity"]
    B --> C{"<b>route_session</b><br/>gateway:exclusive"}
    C -->|"99.5%"| D["Human flow"]
    C -->|"0.1%"| E["Hacker flow"]
    C -->|"0.4%"| F["Bot flow"]
```

---

## Human flow

```mermaid
flowchart TD
    A["<b>initial_human</b><br/>activity"] --> B{"<b>browse_products</b><br/>gateway:exclusive"}
    B -->|"exit"| Z(["<b>session_end</b><br/>event:end"])
    B -->|"not found"| D["<b>not_found</b><br/>activity"]
    B --> C["<b>browse_cat_*</b><br/>activity"]
    D --> B
    C -->|"self-loop"| C
    C -->|"back"| B
    C -->|"exit"| Z
    C --> E["<b>add_to_cart</b><br/>activity"]
    E -->|"exit"| Z
    E --> F["<b>checkout</b><br/>activity"]
    F --> G["<b>thank_you</b><br/>activity"]
    G --> Z
    F --> H["<b>try_again</b><br/>activity"]
    H --> F
```

`initial_human` emits the homepage (`/`) hit and sets session-level properties — IP address, browser user-agent, and HTTP version — which persist unchanged for the rest of the session. Referrers are drawn from a pool weighted toward fitness and outdoor media (YouTube, Reddit, Strava, Runner's World, REI, Garmin).

From `browse_products` the worker selects a product category. Each category state can self-loop (dwell time: 45–150 s, reflecting comparison shopping for equipment), proceed to `add_to_cart`, return to `browse_products`, or exit. The add-to-cart rate per category dwell is 28% and the return-to-browse rate is 32%, reflecting active browsers who compare across multiple categories. `not_found` generates a 404 for out-of-range paths (nutrition, footwear, clothing) and loops back to `browse_products`.

---

## Hacker flow

```mermaid
flowchart LR
    A["<b>hacker_start</b><br/>activity"] --> B["<b>hacker</b><br/>activity"]
    B -->|"99%"| B
    B -->|"1%"| Z(["<b>session_end</b><br/>event:end"])
```

`hacker_start` fires once on session entry (no event emitted) to pin the session-level properties:

| Property | Value |
| --- | --- |
| User-agent | One of: `sqlmap/1.7.8`, `Nikto/2.1.6`, `masscan/1.3`, `zgrab/0.x`, `curl/7.68.0`, `python-requests/2.28.1`, `Go-http-client/1.1`, `Wget/1.21.2` |
| Client IP | Drawn from a pool of **3 IPs** (simulates a single attacker or small botnet) |
| HTTP version | Always `HTTP/1.1` |

The `hacker` state then loops at ~0.01 s interarrival, emitting probe requests with:

- **Paths:** `/.env`, `/.git/config`, `/phpinfo.php`, `/admin/*`, `/wp-admin`, path traversal strings, backup files
- **Query strings:** SQL injection fragments (`?user=admin'--`, `?query=SELECT%20*%20FROM%20users`), `?cmd=whoami`
- **Methods:** GET, POST, PUT, DELETE
- **Status codes:** 400, 401, 403, 404, 500, 502, 503

The loop continues with 99% probability, averaging ~100 probe requests per session before stopping.

---

## Bot flow

```mermaid
flowchart LR
    A["<b>bot_start</b><br/>activity"] --> B["<b>bot</b><br/>activity"]
    B -->|"98%"| B
    B -->|"2%"| Z(["<b>session_end</b><br/>event:end"])
```

`bot_start` fires once on session entry (no event emitted) to pin the session-level properties:

| Property | Value |
| --- | --- |
| User-agent | One of: `Googlebot/2.1`, `bingbot/2.0`, `Applebot/0.1`, `SemrushBot/7`, `AhrefsBot/7.0`, `DotBot/1.2`, `python-requests/2.28.1`, `curl/7.68.0`, `Scrapy/2.11.0` |
| Client IP | Drawn from a pool of **5 IPs** (simulates a crawler's datacenter egress range) |
| HTTP version | Always `HTTP/1.1` |

The `bot` state then loops at ~1 s interarrival, emitting crawl requests with:

- **Paths:** `/robots.txt`, `/sitemap.xml`, `/products`, category index pages, individual product pages
- **Methods:** GET only
- **Status codes:** ~67% 200, ~22% 301, ~11% 404
- **Referrer:** always `-`

The loop continues with 98% probability, averaging ~50 crawl requests per session before stopping.

---

## Volume

The default start interval for workers in this preset is 0.75 seconds, with each worker busy for 792 seconds on average. The maximum number of workers that can be busy at the same time is therefore 792/0.75 = 1,056; increasing available workers (using `-w`) without adjusting how often they begin work (using `-i`) has no effect.

The chart below shows how output scales with workers (varying `-w`) with the preset's default start interval (`--seed 42`, no schedule, PT6H simulated window). To regenerate: `python tools/bench_config_workers.py -c presets/configs/ecommerce_sports.json`.

```mermaid
%%{init: {'themeVariables': {'xyChart': {'plotColorPalette': '#2563eb'}}}}%%
xychart-beta
    title "ecommerce_sports — rows vs -w (PT6H, seed=42)"
    x-axis "-w" [1, 2, 5, 13, 30, 70, 165, 385, 902, 2112]
    y-axis "Rows" 0 --> 420000
    line [387, 719, 1761, 4632, 10683, 24926, 59483, 137493, 315104, 363774]
```

Adjust `-i` and `-w` to model heavier traffic. The table below illustrates how output scales across `-w` and `-i` together (`--seed 42`, no schedule, PT6H simulated window). To regenerate: `python tools/bench_grid.py -c presets/configs/ecommerce_sports.json`.

| `-i` \ `-w` | 1 | 5 | 25 | 100 | 250 | 1,000 | 2,500 | 5,000 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0.01 | ↕️ | ↕️ | ↕️ | ↕️ | ↕️ | 🟥 360,817 (30.6s) | 🟥 901,457 (84.1s) | 🟥 1,803,563 (228.4s) |
| 0.1 | ↕️ | 🟩 1,828 (0.9s) | 🟨 9,230 (1.4s) | 🟧 36,272 (2.8s) | 🟧 90,666 (5.7s) | 🟥 360,495 (21.5s) | 🟥 894,521 (69.2s) | 🟥 1,779,070 (193.7s) |
| 0.75 (default) | ↕️ | 🟩 1,842 (0.4s) | 🟨 9,231 (0.8s) | 🟧 36,011 (2.0s) | 🟧 90,076 (4.4s) | 🟥 345,789 (19.0s) | 🟥 366,513 (20.3s) | ↔️ |
| 1 | 🟩 382 (0.3s) | 🟩 1,816 (0.4s) | 🟨 9,106 (0.7s) | 🟧 35,735 (1.8s) | 🟧 88,990 (4.2s) | 🟥 266,982 (13.9s) | ↔️ | ↔️ |

💥 = thread-creation limit hit. ⏱️ = Timeout. ↔️ = Plateau -- increasing -w had no effect. ↕️ = Plateau -- decreasing -i had no effect. (Ns) = wall-clock seconds for that cell's own run -- not shown for skipped/plateau cells, which were never actually run.
