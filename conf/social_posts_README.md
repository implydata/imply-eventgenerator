# Social Posts Generator

## Quick Start

```bash
# JSON output
python generator.py -c conf/gen/social_posts.json -m 5 -n 100```

## Overview

This configuration generates synthetic social media post data, simulating a feed of user-generated content with engagement metrics. It uses a simple single-state design, making it a good starting point for understanding the generator or for quickly producing tabular data.

## Output fields

| Field | Description | Example |
| --- | --- | --- |
| `__time` | Post timestamp | `2024-01-15T10:30:00.000` |
| `user_id` | Numeric user identifier | `2847` |
| `client_ip` | Poster's IP address | `127.45.12.200` |
| `username` | Display name | `willow`, `rocket`, `miette` |
| `post_title` | Random-character post content (1-140 chars) | `aBcDe_12XY...` |
| `views` | View count (exponential, mean 10000) | `8432` |
| `upvotes` | Upvote count (normal, mean 70, stddev 20) | `73` |
| `comments` | Comment count (normal, mean 10, stddev 5) | `12` |
| `edited` | Whether the post was edited | `True`, `False` |

## State machine

This config uses a single state that loops indefinitely:

```text
state_1 → state_1 (100%)
```

Every worker continuously emits post records at a constant 1-second interval. New workers spawn every 1 second.

## Usage examples

Generate 50 records as JSON:

```bash
python generator.py -c conf/gen/social_posts.json -m 5 -n 50```

Generate a batch of historical data:

```bash
python generator.py -c conf/gen/social_posts.json -m 10 -n 10000 -s "2024-01-01T00:00:00"```

## Use cases

- **Getting started**: Simple config to understand the generator basics
- **Dashboard prototyping**: Quick social media data for building analytics dashboards
- **Engagement analytics**: Test aggregation queries on views, upvotes, and comments
- **Data pipeline testing**: Steady stream of uniform records for throughput testing
