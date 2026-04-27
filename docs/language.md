# The config language

A config is source code. The Python engine is the runtime. The language has first-class primitives for **randomness**, **time**, and **concurrency** — things no general-purpose language treats as primitive because they are incidental to most programs, but central to generating realistic synthetic data.

## What it is

Configs are programs in a domain-specific language. The JSON is the program text. The engine is the interpreter. Writing a config is writing a program that, when run, produces an infinite (or bounded) stream of realistic events.

The language has explicit primitives for the things that matter most in synthetic data:

- **Randomness** — distributions are first-class values on every numeric field. You do not simulate randomness with a loop and a call to `rand()`. You declare it.
- **Time** — `clock` fields and `event:intermediate:timer` states advance simulated time as a first-class operation. Time is not an afterthought derived from a wall clock.
- **Concurrency** — `-m` spawns multiple independent workers. Each worker is an autonomous agent running its own lifecycle simultaneously with all others.

## Language feature inventory

### Implemented

| Feature | How |
| --- | --- |
| Variable namespace | Per-worker dict carried through the full lifecycle. Written by generated and injected variables; read by `"type": "variable"` emitter dimensions. |
| Variables — injected | Subprocess injection writes values directly into the child namespace before each iteration. See [variables-injected.md](variables-injected.md). |
| Variables — generated | `variables` block in `activity` states — generated variables sample values at runtime and write them into the namespace. See [variables-generated.md](variables-generated.md) for all generator types. |
| Randomness / distributions | First-class on every numeric field — `uniform`, `exponential`, `normal`, `constant`, and more. See [distributions](distributions.md) |
| Sequential execution | `next` field on every non-gateway state |
| Probabilistic branching | `gateway:exclusive` — route to one of several next states by weighted probability |
| Iteration (FOR-EACH) | `subprocess:multi:variables` — run a child config once per item in `in`; each item is a list of variable specs (same format as a `variables` block); evaluated at runtime and written into the namespace before each child run |
| Subprocess entry point | `event:start:message` — BPMN Message Start Event; declares that a config is designed for subprocess use; parent injection is applied before this state's own `variables` block runs |
| I/O — emit records | `emitter` on `activity` states. See [emitters](emitters.md) |
| Timed delay / sleep | `event:intermediate:timer` — advance simulated time without emitting |
| Concurrency | `-m` worker pool — each worker is an independent agent running the full lifecycle |

### Not yet implemented

| Feature | Notes |
| --- | --- |
| Subroutines | Call a child config exactly once (no iteration); child receives parent emitters and shares the clock |
| Conditional branching | Branch on a variable value, not just probability — `gateway:exclusive` is probabilistic only |
| Arithmetic / expressions | Derive a field value from other field values |
| Imports / shared libraries | Share emitter definitions, constant blocks, or state fragments across multiple configs |

## Relationship to BPMN

Control flow constructs borrow BPMN naming conventions — `gateway:exclusive`, `event:start:timer`, `subprocess:multi:variables` — because BPMN has well-understood semantics for these patterns.

But this is not a BPMN tool. BPMN models existing processes for documentation and analysis. This language *generates* data. Randomness, time, and concurrency are primitives here — in BPMN they are incidental details, modelled only when the process happens to involve them.
