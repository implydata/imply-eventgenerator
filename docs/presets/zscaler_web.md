# Zscaler Web (NSS-WEB)

Simulates Zscaler Internet Access (ZIA) web/proxy log records for an employee's browsing session — one record per page or request the proxy observed, categorized, security-scanned, and allowed or blocked.

## Quick start

```bash
python generator.py -c presets/configs/zscaler_web.json --template zscalernss-web -n 500 -s "2025-01-01T00:00"

# One day of data
python generator.py -c presets/configs/zscaler_web.json --template zscalernss-web -r P1D -s "2025-01-01T00:00"

# OCSF HTTP Activity (security data lake / SIEM ingestion)
python generator.py -c presets/configs/zscaler_web.json --template ocsf:http_activity -r P1D -s "2025-01-01T00:00"
```

## Templates

| Template | Output |
| --- | --- |
| `zscalernss-web` | Authentic Zscaler NSS feed wire format — tab-delimited `key=value` pairs, matching the `zscalernss-web` Splunk sourcetype |
| `ocsf:http_activity` | [OCSF](https://schema.ocsf.io/) 1.4.0 HTTP Activity (`class_uid` 4002) JSON — one event per transaction, for security data lake / SIEM ingestion |

The `ocsf:http_activity` template derives `activity_id`/`type_uid` from `requestmethod`; `status_id`/`severity_id` follow `action` (`Allowed` → success/informational, `Blocked` → failure, escalated to high severity when `threatcategory` is set and medium otherwise). `urlcategory`/`urlsupercategory`/`urlclass` populate the HTTP request URL's `categories` array; fields with no clean OCSF slot (department, threat/DLP detail, `bwthrottle`, etc.) go in `unmapped`. Verified against the real OCSF 1.4.0 `http_activity` JSON Schema across 17K generated records (0 violations).

## Output fields

| Field | Description |
| --- | --- |
| `datetime` | Transaction timestamp |
| `ClientIP` | Internal client IP address |
| `action` | `Allowed` or `Blocked` |
| `appclass` | Broad application classification |
| `appname` | Recognized application name |
| `bwthrottle` | `YES` if bandwidth-throttled by policy, else `NO` |
| `clientpublicIP` | Public (egress/NAT) IP address the request left the corporate network from |
| `clienttranstime` | Client-side transaction time (ms) |
| `contenttype` | Response content type |
| `department` | Employee's department |
| `devicehostname` | Client device hostname |
| `deviceowner` | Display name of the device owner |
| `dlpdictionaries` | DLP dictionary that matched, or `None` |
| `dlpengine` | DLP engine that fired, or `None` |
| `fileclass` | Broad file classification, or `-` |
| `filename` | Downloaded/uploaded filename, or `-` |
| `filetype` | File type, or `-` |
| `hostname` | Destination hostname |
| `location` | Employee's office/site |
| `md5` | MD5 hash of the file involved, or `-` |
| `pagerisk` | Zscaler page risk score (0-100) |
| `protocol` | `HTTPS` or `HTTP` |
| `reason` | Policy reason for the `action` taken |
| `refererURL` | HTTP referrer, or `-` |
| `requestmethod` | HTTP method |
| `requestsize` | Request size (bytes) |
| `responsesize` | Response size (bytes) |
| `serverip` | Destination server IP address |
| `servertranstime` | Server-side transaction time (ms) |
| `status` | HTTP status code |
| `threatcategory` | Threat category, or `None` |
| `threatclass` | Threat classification, or `None` |
| `threatname` | Matched threat signature name, or `None` |
| `transactionsize` | Total transaction size (bytes) |
| `unscannabletype` | Reason content could not be scanned, or `None` |
| `url` | Request path |
| `urlcategory` | Zscaler URL category |
| `urlclass` | Broad URL classification |
| `urlsupercategory` | Zscaler URL super-category |
| `user` | Employee's login/username |
| `useragent` | Browser user-agent string |

## Destination categories

Each transaction is routed to one of eleven destination profiles, each with its own correlated hostname, category, and security fields:

| Category | Share of traffic | Behavior |
| --- | --- | --- |
| Microsoft 365 | 20% | Allowed, business productivity |
| Salesforce | 7% | Allowed, business productivity |
| Slack | 6% | Allowed, business productivity |
| Search engines | 12% | Allowed |
| News and reference | 8% | Allowed |
| Social networking | 10% | Allowed, monitored |
| Streaming media | 8% | Allowed, occasionally bandwidth-throttled |
| Cloud file storage | 8% | Allowed |
| Cloud file storage (DLP) | 2% | Blocked — outbound DLP policy violation |
| Uncategorized browsing | 14% | Allowed, long-tail of mostly-unique destinations |
| Malicious/phishing | 5% | Blocked — threat detected |

## State machine

Each worker represents one browsing session. The Actor sets session-constant attributes (user, device, location), then loops through a variable number of transactions — dwelling between each — before ending the session.

```mermaid
flowchart LR
    A(["<b>session_start</b><br/>event:start:timer"]) --> B["<b>setup_session</b><br/>activity"]
    B --> C[/"<b>pause_before_request</b><br/>event:intermediate:timer"/]
    C --> D["<b>reset_transaction</b><br/>activity"]
    D --> E{"<b>route_destination</b><br/>gateway:exclusive"}
    E -->|11 categories| F["<b>emit_*</b><br/>activity"]
    F --> G{"<b>route_continue</b><br/>gateway:exclusive"}
    G -->|75%| C
    G -->|25%| H(["<b>session_end</b><br/>event:end"])
```

## Volume

The default start interval for workers in this preset is 5 seconds, with each worker busy for 165 seconds on average. The maximum number of workers that can be busy at the same time is therefore 165/5 = 33; increasing available workers (using `-w`) without adjusting how often they begin work (using `-i`) has no effect.

The chart below shows how output scales with workers (varying `-w`) with the preset's default start interval (`--seed 42`, no schedule, PT6H simulated window). To regenerate: `python tools/bench_config_workers.py -c presets/configs/zscaler_web.json`.

```mermaid
%%{init: {'themeVariables': {'xyChart': {'plotColorPalette': '#2563eb'}}}}%%
xychart-beta
    title "zscaler_web — rows vs -w (PT6H, seed=42)"
    x-axis "-w" [1, 2, 3, 4, 6, 10, 16, 26, 41, 66]
    y-axis "Rows" 0 --> 20000
    line [1110, 2131, 3072, 4150, 6203, 9773, 14398, 17105, 16979, 16979]
```

Adjust `-i` and `-w` to model heavier corporate web traffic. The table below illustrates how output scales across `-w` and `-i` together (`--seed 42`, no schedule, PT6H simulated window). To regenerate: `python tools/bench_grid.py -c presets/configs/zscaler_web.json`.

| `-i` \ `-w` | 1 | 5 | 25 | 100 | 250 | 1,000 | 2,500 | 5,000 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0.01 | ↕️ | ↕️ | 🟨 26,745 (11.3s) | 🟧 108,141 (20.0s) | 🟧 270,440 (37.3s) | 🟥 1,080,327 (141.2s) | 🟥 2,699,778 (414.4s) | ⏱️ |
| 0.1 | 🟩 1,101 (1.1s) | 🟩 5,344 (1.5s) | 🟨 26,826 (3.6s) | 🟧 107,686 (11.0s) | 🟧 269,859 (26.3s) | 🟥 864,224 (88.5s) | ↔️ | ↔️ |
| 1 | 🟩 1,047 (0.4s) | 🟩 5,333 (0.8s) | 🟨 26,356 (2.6s) | 🟧 85,689 (7.6s) | 🟧 86,700 (7.7s) | ↔️ | ↔️ | ↔️ |
| 5 (default) | 🟩 1,041 (0.5s) | 🟩 4,990 (0.7s) | 🟨 17,211 (1.7s) | 🟨 17,226 (1.7s) | ↔️ | ↔️ | ↔️ | ↔️ |

💥 = thread-creation limit hit. ⏱️ = Timeout. ↔️ = Plateau -- increasing -w had no effect. ↕️ = Plateau -- decreasing -i had no effect. (Ns) = wall-clock seconds for that cell's own run -- not shown for skipped/plateau cells, which were never actually run.
