# Clickstream Generator

## Quick Start

```bash
# JSON output
python generator.py -c conf/gen/clickstream.json -m 5 -n 100
# TSV output
python generator.py -c conf/gen/clickstream.json -f conf/form/clickstream_tsv.txt -m 5 -n 100```

## Overview

This configuration generates realistic e-commerce clickstream events that simulate user sessions on a novelty gift shop. Each worker models a single user session, from login through product search and browsing to purchase or cart abandonment.

## Output fields

| Field | Description | Example |
| --- | --- | --- |
| `__time` | Event timestamp | `2024-01-15T10:30:00.000` |
| `user_id` | Numeric user identifier | `2847` |
| `event_type` | Type of user action | `login`, `search`, `view_product`, `purchase` |
| `client_ip` | Client IP address | `127.45.12.200` |
| `client_device` | Device type | `mobile`, `tablet`, `laptop`, `desktop` |
| `client_lang` | User language | `English`, `Spanish`, `Mandarin` |
| `client_country` | User country | `United States`, `Brazil`, `Japan` |
| `referrer` | Traffic source | `google.com/search`, `facebook.com/referring-group` |
| `keyword` | Search keyword used | `gifts`, `Gag gifts`, `kitchen gadgets` |
| `product` | Product being viewed | `Fidget spinner`, `Rubber chicken`, `Magic 8-ball` |

## State machine

Each worker simulates a full user session:

```text
login → home → search ⇄ product → product_detail → addcart → viewcart → purchase
                 ↑          |                                     |
                 └──────────┘                                 dropcart
```

- **login**: User arrives, session variables (IP, device, language, country, referrer) are set and persist throughout.
- **home**: Landing page, 95% proceed to search.
- **search**: User searches for products with keywords. 40% refine their search, 55% view a product.
- **product / product_detail**: User browses product listings and details. 80% of detail viewers add to cart.
- **addcart / viewcart**: Cart management. 25% of cart viewers proceed to purchase, 5% drop items.
- **purchase**: Completed transaction. 50% return to home, 50% end their session.

## Usage examples

Generate 100 records as JSON:

```bash
python generator.py -c conf/gen/clickstream.json -m 5 -n 100```

Generate a batch of historical data:

```bash
python generator.py -c conf/gen/clickstream.json -m 20 -n 10000 -s "2024-01-01T00:00:00"```

Generate deterministic data (same seed = same output):

```bash
python generator.py \
  -c conf/gen/clickstream.json \
  -s "2026-02-12T00:00:00" \
  -r P1D \
  --seed 42
```

## Concurrency (`-m`)

| Little's Law component | Value |
| --- | --- |
| Average session duration (W) | ~1,800 seconds (~30 minutes) |
| Interarrival mean | 0.1s (exponential) |
| Base arrival rate (λ = 1 / mean) | 10 workers/sec |
| Maximum useful `-m` (L = λW) | ~18,000 |

`-m` directly controls peak concurrent users — `-m 500` means up to 500 simultaneous sessions. Sessions are long because the only exit is `purchase → stop` (50% chance), which requires working through the full shopping funnel, so the cap bites immediately and directly determines throughput. The ceiling (~18,000) is simply the maximum the config can sustain; setting `-m` above it has no additional effect, and most use cases will want `-m` well below this figure.

For time-of-day variation, use `--schedule schedule/ecommerce.json`. See the [schedule README](../schedule/README.md) for how schedules interact with `-m` and the ceiling.

## Use cases

- **Funnel analysis**: Track conversion rates through search → product → cart → purchase
- **User behavior modeling**: Understand session patterns, search refinement, and cart abandonment
- **Recommendation testing**: Test product recommendation engines with realistic browsing patterns
- **Real-time analytics**: Stream clickstream events for dashboard and alerting development
