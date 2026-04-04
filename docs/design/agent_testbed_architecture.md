# Event-Driven Autonomous Agent Testbed
## Architecture, Design Decisions, and LangGraph Learning Rubric

---

## Context and Goals

This document captures the design thinking behind an event-driven autonomous agent testbed built
on LangGraph + Temporal + Kafka. It is intended as a reference for Claude Code when implementing
the system.

### Learning objectives
1. Get deeply proficient with LangGraph — all major patterns, not just the basics
2. Build a small set of impressive, publishable demo applications
3. Demonstrate production-grade backend architecture thinking (event buses, durable execution,
   state management) applied to agentic AI

### Why a testbed rather than a real domain application
Building a real domain app at this stage risks spending 80% of effort on domain logic and 20%
on agentic patterns — the wrong ratio for learning. A testbed with mock sensors and actuators
inverts this. The domain is trivial. The agentic patterns are the whole point.

The testbed is itself a publishable artifact. The LangGraph community lacks a well-architected
open-source reference implementation showing the full stack. A good README and a few scenario
scripts make this genuinely shareable.

---

## Domain Choice: Environmental Sensor Network

The testbed uses a **wildfire / environmental monitoring** scenario as its fictional skin.
This domain was chosen because:

- Immediately legible to any audience — no domain expertise required
- Decisions are genuinely hard in ways that resist enumeration ("is this sensor drift or a
  real fire?")
- Multi-agent topology is natural — geographic clusters, specialist agents, a supervisor
- Actuators are clean and visible — alert dispatch, drone tasking, human escalation
- Mock data is easy to generate with interesting scenarios
- The README writes itself: *"A multi-agent system that monitors a distributed sensor network
  and makes escalation decisions under uncertainty"*

### Alternative scenario skins (same architecture, swap sensors/actuators/schema)
- Ocean buoy / environmental sensor network
- Autonomous underwater vehicle fleet
- ICU patient monitoring

The core architecture is domain-agnostic. Scenarios are skins.

---

## Where LLMs Actually Earn Their Place

The key insight from design: LLMs are not useful as workflow executors. Code is better for
anything fully specifiable. The LLM earns its place exactly where full specification breaks down.

**The test:** Can you write an exhaustive if/else tree for this decision? If yes, write code.
If the answer is "it depends on context in ways I can't fully enumerate" — that's the LLM's job.

Specific roles in this testbed:

| Role | Description |
|------|-------------|
| Semantic routing | Classifying anomalies that don't fit clean rules |
| Correlation judgment | "Are these three weak signals a real event or noise?" |
| Significance detection | "Did this amendment change anything that matters?" |
| Situation reporting | Writing human-readable incident summaries |
| Dynamic planning | Multi-hop reasoning where next steps depend on what was found |

The event trigger is always discrete and code-handled. The LLM sits at decision nodes where
branching requires judgment over a space that can't be fully enumerated in advance.

---

## Major Components

```
/core
  /world_engine       ← simulation ground truth
  /sensors            ← sensor base class + types
  /actuators          ← actuator base class + types
  /transport          ← Kafka topics, schemas, bridge consumer
  /agents             ← LangGraph subgraphs + Temporal workflows
  /memory             ← Postgres checkpointer + pgvector store
/scenarios
  /wildfire           ← scenario scripts + sensor configs
  /ocean_buoys        ← (future)
  /auv_fleet          ← (future)
  /icu                ← (future)
/docs
/scripts
```

---

## Component Details

### World Engine

The simulation ground truth that sensors sample from. Agents never see it directly —
the gap between world truth and sensor observations is where interesting agent behavior lives.

**Sub-components:**

| Component | Responsibility |
|-----------|---------------|
| World state | Entities with positions and properties (fire cells, sensor nodes, drones) |
| Sim clock | Tick system with configurable time warp and pause/resume |
| Scenario scripts | Inject events — fires that start and spread, sensor failures, weather changes |
| Physics models | Simple spread / diffusion / drift models (fire spread, smoke diffusion, wind drift) |

**Key design decision:** World state is a shared object that ticks forward. Each tick, physics
models update entity properties. Sensors then sample from this state with configurable noise.
Actuator consequences write back into world state — closing the loop.

A fire spreads. Sensors see it imperfectly. Agents reason about it. A drone gets dispatched.
The drone's coverage changes what sensors can observe. This feedback loop is what makes it a
real system rather than a toy.

---

### Sensor Layer

Sensors sample from the world engine and publish events to Kafka. The sensor base class
provides the interface that both synthetic sensors and real-data replayers implement.

**Base class responsibilities:**
- Sample world state at configurable frequency
- Apply noise model (Gaussian, spike, drift)
- Apply failure mode (see below)
- Publish typed event to Kafka topic

**Failure modes** (these create the interesting test cases for agents):

| Mode | Description |
|------|-------------|
| Stuck | Returns same value indefinitely — simulates frozen sensor |
| Dropout | Stops publishing — simulates connectivity loss |
| Drift | Gradually shifts readings — simulates calibration decay |
| Noise spike | Occasional large outliers — simulates electrical interference |

**Sensor types for wildfire scenario:**
- Temperature
- Smoke density
- Wind speed + direction
- Humidity
- Camera (returns text description for LLM interpretation)

**Source data — synthetic vs real:**

Start synthetic. Real data adds demo value later but slows early development and removes
ground truth (you can't verify agent decisions against real data as easily). NOAA buoy data
and USGS fire perimeter data are freely available for future integration. The sensor base
class interface is the same either way.

---

### Actuator Layer

Actuators receive structured commands from agents and apply consequences to world state.
They are the "output" side of the system — what agents actually do.

**Base class responsibilities:**
- Receive command message from command bus (Kafka topic)
- Validate command schema
- Log command receipt (full audit trail)
- Apply consequence to world state
- Publish result event (success/failure + state change)

**Actuator types for wildfire scenario:**
- Alert dispatch — sends notification, logs recipient and urgency
- Drone tasking — moves drone entity in world state, changes sensor coverage
- Human escalation — triggers interrupt() in Temporal workflow, pauses for approval
- Suppression resource request — changes world state (water drop reduces fire intensity)

**Critical design note:** Actuator consequences write back to world state. This is what closes
the loop. Without this, agents are shouting into a void.

---

### Data Transport

Two buses, kept strictly separate:

| Bus | Direction | Contents |
|-----|-----------|----------|
| Sensor event bus (Kafka) | Sensors → Agents | Sensor readings, anomaly events |
| Command bus (Kafka) | Agents → Actuators | Structured actuator commands |
| Result bus (Kafka) | Actuators → Agents | Command outcomes, state changes |

**Canonical sensor event schema** (every sensor reading has these fields):

```python
class SensorEvent(BaseModel):
    event_id: str           # UUID
    sensor_id: str          # stable sensor identifier
    sensor_type: str        # "temperature" | "smoke" | "wind" | ...
    cluster_id: str         # geographic cluster this sensor belongs to
    timestamp: datetime     # wall clock time of reading
    sim_tick: int           # simulation tick (for replay/debug)
    value: float | dict     # reading value(s)
    confidence: float       # 0.0-1.0, set by sensor based on health
    metadata: dict          # sensor-specific extras
```

**Topic design:**

```
sensors.raw.{cluster_id}     ← raw readings per cluster
events.anomaly               ← agent-detected anomalies
agents.decisions             ← agent decision log (audit)
commands.actuators           ← agent → actuator commands
results.actuators            ← actuator outcomes
```

---

### Agent Layer

Built on LangGraph subgraphs, orchestrated by Temporal, triggered by Kafka events via a
thin bridge consumer.

**Bridge consumer** (the Kafka → Temporal handoff):
- Reads from `sensors.raw.*` topics
- Calls `temporal_client.start_workflow()` or `signal_workflow()`
- Commits Kafka offset only after Temporal ACK
- Uses `{topic}:{partition}:{offset}` as workflow ID for natural deduplication
- `enable.auto.commit=false`
- `WorkflowIdReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY`

**Agent topology:**

```
Cluster agents (one per geographic cluster)
  ↓ reports findings
Supervisor agent
  ↓ dispatches commands
Actuators
```

**Cluster agent responsibilities:**
- Maintain rolling window of sensor readings for their cluster
- Detect anomalies (LLM classification node)
- Correlate readings across sensors in cluster
- Assess confidence
- Report findings to supervisor

**Supervisor agent responsibilities:**
- Receive findings from all cluster agents (parallel fan-out via Send API)
- Cross-cluster correlation
- Priority decision (which events warrant action)
- Actuator command generation (structured output)
- Human escalation decision (triggers interrupt())
- Situation report generation

**Memory architecture:**

| Layer | Technology | Contents |
|-------|-----------|----------|
| Within-run state | LangGraph checkpointer (Postgres) | Workflow execution state, crash recovery |
| Cross-agent shared | LangGraph Store | Incident history visible to all agents |
| Semantic recall | pgvector | Past incidents for similarity search |

---

## Kafka ↔ Temporal Integration

### The core problem
There is no native transaction across Kafka and Temporal. The bridge consumer can crash
between calling Temporal and committing the Kafka offset.

### The solution
Three rules make it robust:

1. `enable.auto.commit=false` — manual offset control
2. Call Temporal, wait for ACK, *then* commit offset
3. Use `{topic}:{partition}:{offset}` as workflow ID — natural dedup key

When Kafka re-delivers (at-least-once) and the bridge calls `start_workflow()` again with
the same ID, Temporal returns "already exists" — no duplicate work, no special handling needed.

### Two integration patterns

**Pattern 1 — Fire and start:** Each Kafka event starts a new Temporal workflow execution.
Use when: each event represents a discrete task (new anomaly to investigate).

**Pattern 2 — Signal a running workflow:** Kafka event updates a long-running agent.
Use when: events are updates to an agent's world (new data arrives, dependency resolves).

Temporal deduplicates signals automatically via request ID.

### Outbound direction (Temporal → Kafka)
When agents publish results back to Kafka as events, include an idempotency key in the
message header: `{workflow_run_id}:{activity_attempt}`. Downstream consumers deduplicate
on this key.

---

## Why Temporal (Not a Custom Consumer)

The naive approach — write a Kafka consumer that calls LangGraph — fails in production
because you end up hand-rolling retries, deduplication, state tracking, and timeouts.
Six months later you have a fragile bespoke orchestration engine.

Temporal provides:
- Durable execution — workflows survive worker crashes, resume exactly where they left off
- Activity retries with configurable backoff — without code
- Signals — external events (including Kafka) wake up sleeping workflows
- `interrupt()` — pause indefinitely for human approval, resume on demand
- Full execution history — audit trail and time travel for debugging
- Postgres backend — stays in your existing data stack

**Temporal concepts mapped to this system:**

| Temporal concept | Role in testbed |
|-----------------|-----------------|
| Workflow | Cluster agent or supervisor agent lifetime |
| Activity | Single LangGraph subgraph invocation, tool call, or actuator command |
| Signal | Kafka event waking a running agent |
| `interrupt()` | High-confidence alert pausing for human approval |
| Checkpointer | Postgres — workflow state survives crashes |
| Worker | Process hosting LangGraph code — runs on your infra |

**Determinism requirement:** Temporal workflow code must be deterministic. No direct I/O,
no `datetime.now()`, no randomness. All non-deterministic work (LLM calls, database queries,
sensor reads) goes in Activities. LangGraph subgraph invocations are Activities.

---

## LangGraph Skills Rubric

Organized by topic. Levels: **foundational** (can explain), **mid-level** (has used in anger),
**advanced** (can reason about tradeoffs).

Coverage in testbed: **covered** / **partial** / **not yet**

---

### 1. Graph Primitives

| Skill | Level | What an interviewer wants to hear | Testbed coverage | Where |
|-------|-------|----------------------------------|-----------------|-------|
| StateGraph + TypedDict state | foundational | State is the single shared object; nodes read and return partial updates; reducers merge them | covered | Every subgraph — sensor cluster agent, supervisor |
| Nodes — functions vs runnables | foundational | Any callable works; runnables give streaming + observability for free | covered | All agent nodes |
| Edges — normal vs conditional | foundational | Conditional edge is a function on state; must return a node name or END | covered | Routing after anomaly classification |
| Reducers and Annotated state | mid-level | Default reducer overwrites; `add_messages` appends; custom reducers handle merging concurrent node outputs | covered | Merging readings from parallel sensor nodes |
| Compile + invoke / stream | foundational | `compile()` locks the graph; `stream()` yields `(node, state)` tuples for observability | covered | All graph entry points |

---

### 2. Control Flow

| Skill | Level | What an interviewer wants to hear | Testbed coverage | Where |
|-------|-------|----------------------------------|-----------------|-------|
| Cycles / loops | mid-level | Unlike DAGs — LangGraph supports cycles; used for retry, reflection, tool-use loops; needs explicit termination condition | covered | Agent retries ambiguous sensor reading before escalating |
| Parallel node execution (Send API) | mid-level | `Send()` dispatches dynamic fan-out; results merged by reducer; replaces static parallel edges for dynamic targets | covered | Supervisor fans out to N cluster agents simultaneously |
| Dynamic branching | mid-level | Branch target determined at runtime from state; can route to subgraphs or tool nodes | covered | Classify anomaly → route to wildfire / sensor-fault / weather branch |
| Recursion limit + error handling | advanced | `recursion_limit` in config; `GraphRecursionError`; design termination conditions deliberately | partial | Needs explicit scenario — runaway reflection loop |

**Note on Send API:** This is the skill that most separates "I've used LangGraph" from
"I understand LangGraph's execution model." The supervisor dispatching to N cluster agents
in parallel is the perfect natural exercise for it. Prioritize this.

---

### 3. Tools

| Skill | Level | What an interviewer wants to hear | Testbed coverage | Where |
|-------|-------|----------------------------------|-----------------|-------|
| Tool definition — `@tool` decorator | foundational | Docstring becomes the tool description; type hints become the schema; LLM sees both | covered | `get_sensor_history`, `query_world_state`, `dispatch_drone` |
| ToolNode + `bind_tools` | foundational | `ToolNode` executes tool calls from `AIMessage`; `bind_tools` attaches schema to LLM; standard ReAct loop | covered | Cluster agent tool loop |
| Tool errors + fallback | mid-level | `ToolNode` catches exceptions and returns `ToolMessage` with error; agent can retry or route differently | partial | Sensor timeout → error message → agent decides to use cached reading |
| Structured output tools | mid-level | `with_structured_output()` forces schema; use for actuator commands that must be validated before execution | covered | Actuator command schema — agent must produce valid `DroneCommand` |

---

### 4. Memory and Persistence

| Skill | Level | What an interviewer wants to hear | Testbed coverage | Where |
|-------|-------|----------------------------------|-----------------|-------|
| Checkpointers — in-memory vs Postgres | mid-level | `MemorySaver` for dev; `PostgresSaver` for prod; `thread_id` is the resume key; state survives crashes | covered | All persistent agents; crash recovery scenarios |
| Thread-level vs cross-thread memory | mid-level | Checkpointer = within a run; Store = shared across runs and agents; different access patterns | covered | Supervisor shares incident history across cluster agents via Store |
| Long-term memory with Store + embeddings | advanced | `InMemoryStore` / custom Store; semantic search over past decisions; pgvector integration | partial | Agent recalls similar past incidents — needs pgvector scenario |
| State schema evolution | advanced | Adding fields to TypedDict with defaults; migration strategy for persisted checkpoints | not yet | Not in testbed — separate exercise |

---

### 5. Multi-Agent

| Skill | Level | What an interviewer wants to hear | Testbed coverage | Where |
|-------|-------|----------------------------------|-----------------|-------|
| Subgraphs — compile and invoke | mid-level | Subgraph compiled separately; invoked as a node; has its own state schema; parent maps state in/out | covered | Each cluster agent is a compiled subgraph |
| State schema handoff between graphs | mid-level | Parent and subgraph states are different types; explicit mapping node transforms between them | covered | Supervisor state → ClusterAgentState mapping |
| Supervisor pattern | mid-level | Supervisor node routes to specialist agents; aggregates results; decides next action; owns termination | covered | Supervisor agent — core of the testbed |
| Agent handoff / swarm pattern | advanced | Agents pass control peer-to-peer via `Command`; no central supervisor; emergent coordination | partial | Cluster agents handing off to a specialist — needs explicit scenario |

---

### 6. Human-in-the-Loop

| Skill | Level | What an interviewer wants to hear | Testbed coverage | Where |
|-------|-------|----------------------------------|-----------------|-------|
| `interrupt()` — pause and resume | mid-level | `interrupt()` suspends graph at any node; state persisted; resume by invoking with same `thread_id` + new input | covered | High-confidence alert pauses for human approval before actuator fires |
| State editing before resume | advanced | Human can modify state before resuming; agent sees corrected state as if it had always been that way | partial | Human overrides agent's classification before escalation fires |
| Time travel / replay | advanced | `get_state_history()` returns all checkpoints; can re-invoke from any past checkpoint; fork execution | not yet | High value — replay incident from checkpoint to try different response |

**Note on `interrupt()` + Temporal:** This is the most impressive demo moment. Agent pauses
mid-execution waiting for human approval. Temporal keeps the workflow alive indefinitely.
Human clicks approve. Execution resumes. Any non-technical audience immediately understands
why this matters.

**Note on time travel:** Not yet in the testbed but high priority to add. The ability to
say "here's the incident — let me rewind to 10 minutes earlier and run a different response"
is genuinely jaw-dropping in a demo. It's a scenario script addition, not an architecture change.

---

### 7. Streaming and Observability

| Skill | Level | What an interviewer wants to hear | Testbed coverage | Where |
|-------|-------|----------------------------------|-----------------|-------|
| `stream_mode` — values vs updates vs debug | mid-level | `values` = full state each step; `updates` = delta only; `debug` = everything including LLM tokens | covered | Live dashboard showing agent reasoning as it happens |
| LangSmith tracing | mid-level | `LANGCHAIN_TRACING_V2=true`; traces every node, LLM call, tool call; critical for debugging multi-agent | covered | Always on — non-negotiable for debugging the testbed |
| Custom callbacks | advanced | `BaseCallbackHandler`; emit metrics, custom logs, or side effects at any node or LLM call | partial | Emit Kafka events from agent decisions — closes the feedback loop |

---

## Skills Gap Summary

### Well covered by the testbed naturally
Graph primitives, conditional routing, tool loop, ToolNode, structured output, checkpointing,
thread vs cross-thread memory, subgraphs, supervisor pattern, Send API fan-out,
interrupt() / human-in-the-loop, streaming, LangSmith tracing.

### Needs explicit scenario design
- Recursion limit / runaway loop handling
- Tool error fallback (sensor timeout scenario)
- Agent handoff / swarm pattern
- State editing before resume
- Long-term memory with pgvector similarity search
- Custom callbacks emitting to Kafka

### Not in testbed — separate exercises
- State schema evolution / migration
- Time travel (high value to add — it's a scenario, not an architecture change)

---

## Recommended Build Order

1. World engine — tick system, entity model, basic fire spread physics
2. Sensor base class + 2-3 sensor types, synthetic only
3. Kafka topics + canonical event schema
4. Single cluster agent as LangGraph graph with ToolNode loop
5. Temporal worker hosting the cluster agent as an Activity
6. Bridge consumer (Kafka → Temporal, with dedup)
7. Actuator base class + alert dispatch actuator (writes back to world state)
8. Supervisor agent with Send API fan-out to cluster agents
9. Postgres checkpointer + crash recovery scenario
10. interrupt() scenario — high-confidence alert requiring human approval
11. Cross-agent Store for shared incident history
12. LangSmith tracing throughout
13. Scenario scripts — sensor fault, real fire, simultaneous events
14. pgvector memory for past incident recall
15. Time travel scenario

Build order follows the rubric skill progression — each step exercises the next level
of LangGraph capability.

---

## Tech Stack Summary

| Layer | Technology | Notes |
|-------|-----------|-------|
| Event bus | Kafka | Sensor events, commands, results |
| Durable execution | Temporal | Worker orchestration, crash recovery, HITL |
| Agent framework | LangGraph | Subgraphs, state, tool loops |
| LLM | Anthropic Claude (via API) | Classification, correlation, planning |
| Persistence | Postgres | Temporal backend + LangGraph checkpointer |
| Vector memory | pgvector | Semantic incident recall |
| Observability | LangSmith + Temporal UI | Agent traces + workflow execution history |
| Language | Python | Temporal Python SDK + LangGraph |

---

*Document generated from design conversation — intended as context for Claude Code implementation.*
