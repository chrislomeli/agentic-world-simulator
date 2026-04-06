# Episode 1, Session 5: The Bridge to Agents

> **What we're building:** An async consumer that pulls sensor events off the queue, batches them by cluster, and invokes the agent graph.
> **Why we need it:** Sessions 03–04 built the producer side — sensors emit events, the publisher puts them on a queue. This session builds the consumer side — the component that reads events off the queue and hands them to agents. This is the bridge between the observation layer (sensors) and the reasoning layer (agents).
> **What you'll have at the end:** A complete async pipeline from world tick → sensor emission → queue → consumer → agent invocation, with a stub agent that proves the plumbing works before we build the real LangGraph agent in Session 06.

---

## Why the bridge consumer matters

Sessions 03–04 gave you a producer pipeline:

```
world.tick() → sensors.emit() → queue.put(event)
```

Events are piling up in the queue. Nothing is reading them yet.

This session builds the consumer side:

```
queue.get(event) → buffer by cluster_id → agent_graph.invoke(state)
```

The `EventBridgeConsumer` is the component that sits between the transport layer (the queue) and the agent layer (LangGraph). It reads events one at a time, groups them by `cluster_id`, and invokes the cluster agent graph when a batch is ready.

The name "bridge" is intentional. This component bridges two different architectural layers:
- **Transport layer** — async queues, event envelopes, routing keys. Domain-agnostic. Works for any event-driven system.
- **Agent layer** — LangGraph state machines, tool calls, LLM reasoning. Domain-specific. Only knows about the agent's state schema.

The bridge consumer translates between them. It reads `SensorEvent` objects (transport schema) and constructs `ClusterAgentState` dicts (LangGraph schema). The agent never sees a `SensorEvent` directly — it only sees the state dict the consumer builds.

This separation is what makes the system composable. You can swap the transport layer (replace the queue with Kafka) without touching the agent. You can swap the agent (replace the cluster agent with a different graph) without touching the transport. The bridge is the only place that knows about both.

---

## EventBridgeConsumer: the async read loop

Here's what the consumer does each iteration:

1. **Read one event** from the queue via `await queue.get()`
2. **Buffer it** in a per-cluster list: `buffers[cluster_id].append(event)`
3. **Check batch size** — if the buffer for this cluster has reached `batch_size`, invoke the agent
4. **Invoke the agent** — construct a state dict, call `agent_graph.invoke(state)`, collect findings
5. **Mark the event done** via `queue.task_done()`

The consumer runs in an async loop. It blocks on `queue.get()` when the queue is empty, and it blocks on `agent_graph.invoke()` when the agent is running (potentially waiting on an LLM call). The async structure means multiple consumers could run in parallel without blocking each other, though in this demo we only run one.

Here's the minimal setup:

```python
from bridge.consumer import EventBridgeConsumer

consumer = EventBridgeConsumer(
    queue=queue,
    agent_graph=cluster_agent_graph,
    batch_size=3,
)

await consumer.run(max_events=100)  # consume 100 events, then stop
```

The consumer will read events until it hits the limit, then flush any partial batches and return. You can also run it with no limit (`max_events=None`) and call `consumer.stop()` from another task to shut it down cleanly.

---

## Batching: why events accumulate before invocation

The consumer doesn't invoke the agent for every single event. It batches them.

**Why batch?** Because LLM calls are expensive (time and cost). If you invoke the agent once per event, and you have 50 sensors emitting every tick, you're making 50 LLM calls per tick. That's slow and expensive.

Batching lets the agent see multiple events at once:

```python
state = {
    "sensor_events": [event1, event2, event3],  # ← batch of 3
    "trigger_event": event3,                    # ← most recent
    ...
}
```

The agent can correlate across events. It can see that temperature spiked at position (7, 2) *and* smoke increased at position (7, 3) *and* wind is blowing northeast — all in one invocation. That's more context than seeing each event in isolation.

The `batch_size` parameter controls this. Set it to 1 for immediate response (one invocation per event). Set it to 5–10 for better correlation at the cost of latency. The right value depends on your scenario.

**Per-cluster batching:** Events are buffered separately for each `cluster_id`. If you have two clusters (`cluster-north` and `cluster-south`), each maintains its own buffer. When `cluster-north` reaches batch size 3, its agent is invoked. `cluster-south` might still be at batch size 1. They're independent.

This is the foundation for the multi-agent architecture in Sessions 09–10. Each cluster has its own agent graph. The consumer routes events to the right agent based on `cluster_id`. The supervisor agent (Session 09) will aggregate findings across all cluster agents.

---

## State construction: the handoff to LangGraph

The consumer constructs the initial LangGraph state in `_invoke_agent()`:

```python
state = {
    "cluster_id": cluster_id,
    "workflow_id": f"{cluster_id}::bridge-{self.invocations}",
    "sensor_events": events,      # ← all buffered events for this cluster
    "trigger_event": events[-1],  # ← most recent event (the one that triggered invocation)
    "messages": [],               # ← LangGraph message list (empty initially)
    "anomalies": [],              # ← findings will accumulate here
    "status": "idle",             # ← workflow status
    "error_message": None,
}

result = self._agent_graph.invoke(state)
```

This is the contract between the bridge and the agent. The agent expects a dict with these fields. The bridge provides them. The agent doesn't know where the events came from (queue, Kafka, file replay). The bridge doesn't know what the agent does with them (LLM reasoning, rule-based classification, stub logic).

**Key insight:** Events don't "stream" into the graph. They're passed as a batch in the initial state. The graph runs once, processes all events, and returns. If you want the graph to see more events, you invoke it again with a new batch. This is different from a streaming architecture where events flow continuously through a long-running process. LangGraph is invocation-based, not streaming-based. The consumer adapts the streaming queue to the invocation model.

---

## Findings collection: what comes back

After the agent runs, the consumer extracts findings from the result state:

```python
result = self._agent_graph.invoke(state)
findings = result.get("anomalies", [])

for finding in findings:
    self.collected_findings.append(finding)
    if self._on_finding:
        self._on_finding(finding)  # optional callback
```

Each finding is an `AnomalyFinding` object (defined in `agents/cluster/state.py`). It contains:
- `cluster_id` — which cluster detected this
- `anomaly_type` — classification (e.g. "temperature_spike", "smoke_detected")
- `severity` — Low / Medium / High / Critical
- `confidence` — 0.0–1.0, how confident the agent is
- `description` — human-readable explanation
- `affected_sensors` — list of sensor IDs involved
- `recommended_actions` — list of suggested responses

The consumer collects all findings in `self.collected_findings` so you can inspect them after the run completes. It also calls the optional `on_finding` callback for each one, which is useful for logging or forwarding findings to the supervisor agent (Session 09).

---

## Running the full pipeline

Here's a complete script that wires publisher → queue → consumer with a stub agent:

```python
import asyncio
from domains.wildfire import create_basic_wildfire
from domains.wildfire.sensors import TemperatureSensor, SmokeSensor
from world.sensor_inventory import SensorInventory
from sensors import SensorPublisher
from transport import SensorEventQueue
from bridge.consumer import EventBridgeConsumer

# Stub agent graph (Session 06 will build the real one)
def build_stub_graph():
    """Minimal graph that just echoes the state back."""
    from langgraph.graph import StateGraph
    
    def stub_node(state):
        # Pretend to detect an anomaly
        state["anomalies"] = [{
            "cluster_id": state["cluster_id"],
            "anomaly_type": "stub_detection",
            "severity": "Low",
            "confidence": 1.0,
            "description": f"Stub detected {len(state['sensor_events'])} events",
        }]
        state["status"] = "completed"
        return state
    
    graph = StateGraph(dict)
    graph.add_node("stub", stub_node)
    graph.set_entry_point("stub")
    graph.set_finish_point("stub")
    return graph.compile()

# Setup
engine = create_basic_wildfire()
queue = SensorEventQueue()
inventory = SensorInventory(grid_rows=10, grid_cols=10)

# Add sensors
for row, col in [(2, 2), (5, 5), (7, 7)]:
    temp = TemperatureSensor(
        source_id=f"temp-{row}-{col}",
        cluster_id="cluster-north",
        engine=engine,
        grid_row=row,
        grid_col=col,
    )
    inventory.register(temp, row=row, col=col)

# Publisher and consumer
publisher = SensorPublisher(
    inventory=inventory,
    queue=queue,
    engine=engine,
    tick_interval_seconds=0.1,
)

consumer = EventBridgeConsumer(
    queue=queue,
    agent_graph=build_stub_graph(),
    batch_size=3,
)

# Run pipeline
async def main():
    # Producer: run for 10 ticks
    await publisher.run(ticks=10)
    print(f"Publisher done: {queue.total_enqueued} events enqueued")
    
    # Consumer: process all events
    await consumer.run(max_events=queue.total_enqueued)
    print(f"Consumer done: {consumer.events_consumed} events consumed")
    print(f"Agent invocations: {consumer.invocations}")
    print(f"Findings: {len(consumer.collected_findings)}")
    
    # Inspect findings
    for finding in consumer.collected_findings:
        print(f"  - {finding['anomaly_type']}: {finding['description']}")

asyncio.run(main())
```

You should see output like:

```
Publisher done: 30 events enqueued
Consumer done: 30 events consumed
Agent invocations: 10
Findings: 10
  - stub_detection: Stub detected 3 events
  - stub_detection: Stub detected 3 events
  ...
```

3 sensors × 10 ticks = 30 events. Batch size 3 → 10 invocations (30 / 3). Each invocation produces one finding. The stub graph is trivial, but the plumbing works.

---

## Why this session has no LangGraph yet

You might notice the stub graph above doesn't use any LangGraph features — no tools, no LLM, no ReAct loop. That's intentional.

This session is about the *plumbing* — the async producer/consumer pipeline, the batching logic, the state construction. The agent is a black box. As long as it accepts a state dict and returns a state dict, the consumer doesn't care what's inside.

Session 06 will replace the stub with a real LangGraph agent that has:
- A proper `ClusterAgentState` TypedDict schema
- Nodes for classification, analysis, and reporting
- Conditional edges based on anomaly detection
- Tool calls (in Session 07 when we add LLM mode)

But the consumer won't change. It will still construct the same state dict, call `invoke()`, and extract findings. The contract is stable. That's the design.

---

## What this session unlocks

After Session 04, you had a producer pipeline that emits events into a queue.

After Session 05, you have a complete async pipeline:

```
world.tick() → sensors.emit() → queue.put() → queue.get() → agent.invoke() → findings
```

Every piece is wired. The producer runs, events flow through the queue, the consumer reads them, the agent (stub for now) processes them, and findings come out the other end.

Sessions 06–07 will replace the stub agent with a real cluster agent (stub mode in 06, LLM mode in 07). Sessions 08–10 will add the supervisor agent and wire the full multi-agent system. But the transport plumbing — the queue and the bridge consumer — is done. It won't change again.

---

## Key files

- `src/transport/queue.py` — `SensorEventQueue`: async queue, back-pressure, typed interface
- `src/bridge/consumer.py` — `EventBridgeConsumer`: async read loop, per-cluster batching, state construction, agent invocation, findings collection

---

*Next: Session 06 builds the cluster agent graph in stub mode — a LangGraph StateGraph with typed state, nodes for classification and reporting, and conditional edges. No LLM yet, just hardcoded logic to prove the graph structure works. Session 07 will add the LLM and tool calls to make it actually reason about sensor events.*
