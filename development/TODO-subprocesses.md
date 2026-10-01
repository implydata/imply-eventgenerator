# Subprocesses

An idea that might be worth building, not committed work. It was tried from
April to May 2026 on the `202604-looping` branch, which was deleted on
2026-10-01. Nothing from that branch survives except these notes, so any future
attempt starts from main.

## The idea

Let one config call another as a step in its state machine, optionally once per
item in a list. A browser session is the motivating case: a page view isn't one
request but many (HTML, CSS, JavaScript, images). Modelling a store's journey of
homepage, category listing with thumbnails, product detail, add to cart, and
checkout in one config grew it to about 80 states, which is what led to calling
child configs: one config per product category, each handling its own browse,
view, and add-to-cart flow, with a shared add-to-cart config callable from any
of them. Child configs would also let presets share fragments, such as a hacker
or bot Actor, instead of copying them.

## How the approach evolved

1. **Constants.** The first commit added a top-level `constants` block: named
   values loaded into every session's variables before the state machine
   started. The same day it was renamed `variable_defaults`, because that's all
   it was, and later it was removed. Defaults moved to the parent's `items` and
   to a `variables` block on the child's entry state. Repeated literal values
   are a different problem, now a separate item in [TODO.md](TODO.md):
   load-time definitions.
2. **Loops.** `subprocess:multi_instance` ran a child config once per entry in
   an `in` list, but only used the list's length. It became
   `subprocess:multi:variables`, whose `items` entries each set variables before
   their child run. A plain `subprocess` state, which runs a child once, came
   later.
3. **Child configs.** A child's entry point became `event:start:message` (named
   after the BPMN message start event). Children inherited the parent's
   emitters and could add their own.
4. **Building values.** `variable:template`, a Jinja template rendered against
   the session's variables (with `StrictUndefined`, so a missing variable is an
   error), let a child build values such as
   `/images/{{ var_category }}/{{ var_asset_name }}-thumb.jpg` from what its
   parent passed in. It worked in emitter `dimensions` and in `variables`
   blocks, where it could read variables set earlier in the same block.
5. **A proving ground.** A DIY hardware-store preset was built with child
   configs throughout, starting with a looping state that took some time to get
   right. See [DIY preset](#diy-preset).
6. **Outcome.** The engine code was thread-based, and the engine moved to a
   single-threaded simpy event loop in September 2026, so the code couldn't be
   kept. The parts that stood alone were rebuilt on main instead: the
   `static`/`variable`/`generator:<class>` dimension kinds, and one class per
   state type. A trial merge of main into the branch showed it couldn't be
   salvaged by merging: the engine conflicts could only be resolved by writing
   the port inside the merge commit, git's handling of main's earlier reverts
   silently dropped content, and presets ended up split across two type-name
   schemes.

The branch also had `docs/language.md`, a feature list for the config language,
and a README paragraph introducing it: "A config is source code. The engine is
a runtime. The language has first-class primitives for randomness, time, and
concurrency — things no general-purpose language treats as primitive because
they are incidental to most programs but central to this one." Both would need
rewriting for current main.

## Design as built

```json
{
  "name": "load_components",
  "type": "subprocess:multi:variables",
  "config": "presets/configs/child.json",
  "items": [
    [
      { "name": "url", "type": "static", "value": "/index.html" },
      { "name": "bytes", "type": "static", "value": 1247 }
    ],
    [
      { "name": "url", "type": "static", "value": "/static/style.css" },
      { "name": "bytes", "type": "static", "value": 8432 }
    ]
  ],
  "next": "done"
}
```

- Each `items` entry is a list of variable specs in the same format as an
  activity's `variables` block, evaluated into the session's variables before
  that child run.
- `event:start:message` has no `cardinality_distribution`, because the parent
  triggers it. A child with no `event:start:timer` correctly fails standalone
  validation, and calling a config with no `event:start:message` raised a clear
  error.

## Problems to solve if it's revisited

- Child config paths were resolved from the current working directory, not from
  the parent config's location.
- `validate.py` never opened child config files, so their errors only showed up
  at run time.
- Children wrote straight into the parent's variables, with no separate scope.
- `items` was a hand-written list. The DIY preset spelled out 77 entries in
  full.
- The benchmark tools don't know about child state machines.
- Output from the branch's loop test config wasn't reproducible with `--seed`
  and `-s`, and the cause was never found.
- The engine runs each session as a simpy generator, so a child must run as a
  nested generator on top of the `StateBase` subclasses in `ieg/states.py`.
  Start by extracting two pieces from `DataDriver`, which are currently inline
  in `DataDriver.__init__` and `session_process`: a generator that runs a
  states dict from a given entry state against a given variables dict, and a
  function that parses a list of state dicts with a given set of emitters. The
  branch called these `run_state_machine` and `_parse_states`.
- `fmt_config.py` sorts every `variables` block by type and then by name. Once a
  template can read another variable in the same block, that reordering can
  break evaluation order. Either stop sorting `variables` blocks, or have
  `validate.py` flag a template that reads a variable defined later in the
  block.
- Asset loading can swamp the output: see [Volume effects](#volume-effects) and
  the DIY preset's asset share.

## Volume effects

In an April experiment, adding three asset loads per browse event to
`ecommerce.json` raised PT6H output (seed 42) from about 265,000 to 615,000
rows, about 2.3 times, while the `-w` ceiling stayed at about 2,112. Little's
Law explains this: the asset loads add 0.03 to 0.45 seconds to each session,
which is negligible against 90 to 300 seconds of browse pauses, so concurrency
barely changes while rows per browse event go from one to four.

When a subprocess adds iterations, estimate the session duration before and
after. If the added delay is small next to the dominant pauses, the ceiling is
unaffected and volume grows in proportion to the extra rows.

## DIY preset

A hardware-store ecommerce preset with an entry config, one child config per
category (power tools, hand tools, plumbing, electrical, paint, lumber,
garden), and shared child configs for static files, image loading, add to
cart, the hacker, and the bot.

- **Routing:** 99.7% human, 0.1% hacker, 0.2% bot. The human path loads static
  files and preloads images, then browses categories. After each category,
  45% browse again, 30% go to checkout, and 25% end; 65% of checkouts complete.
  Within a category: 75% view a product, then 25% view another, 15% go back to
  browsing, 45% add to cart, and 15% exit.
- **Pauses:** category browsing took 20–60 seconds for power tools, 25–75
  seconds for plumbing and electrical, and 15–45 seconds for the rest.
- **Assets:** JavaScript and CSS once per session (30–500 KB), 77 thumbnails
  once per session (4–35 KB), and a hero and two gallery images per product
  view (80–600 KB). The first version loaded 11 thumbnails and 3 static files on
  every category page visit. A full-day run (PT24H, `-m 500`, the standard
  ecommerce schedule) produced 2.8 million rows, 82% of them asset requests: 66%
  category thumbnails and 16% static JavaScript and CSS, which buried the page
  requests. A one-off preload at session start replaced the per-visit loads. It
  was a shortcut to make progress, not a model of how browsers cache assets, and
  it still left about 88% of rows as image hits in a PT1H run, roughly 84 per
  session.
- **`bytes_out`:** set by every emitting activity: homepage 5–80 KB, category
  8–60 KB, product 10–80 KB, checkout 5–30 KB, thank-you 3–20 KB, cart API
  200 B–2 KB, bot crawl 5–80 KB, and hacker error responses 200 B–5 KB.
- **Hacker and bot:** the hacker probed about every 0.01 seconds across 40
  suspicious paths with error status codes; the bot crawled about once a second
  through `robots.txt`, the sitemap, and category and product pages.
- **Never finished:** the `-w` benchmark, the preset doc, and a
  `tools/generate_all.json` profile. The benchmark mattered most: the point of
  the preset was the volume it generates, and that was never measured against
  the existing ecommerce presets. Ideas not built: updating the referrer
  within a session, 304 responses for repeat visitors' assets, and POST for
  cart adds.
