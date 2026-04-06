# Episode 2, Session 6: The Agent Graph (Stub Mode)

> **What we're building:** A LangGraph StateGraph with typed state, nodes, and conditional edges — no LLM yet, just deterministic logic to prove the graph structure works.
> **Why we need it:** Sessions 03–05 built the infrastructure to get sensor events to the agent. This session builds the agent itself — the LangGraph state machine that classifies sensor readings into anomaly findings. We start with a stub (hardcoded logic) to learn the graph primitives before adding the LLM in Session 07.
> **What you'll have at the end:** A compiled cluster agent graph that accepts sensor events, runs through three nodes (ingest → classify → report), and produces structured findings — all with deterministic stub logic you can trace step by step.

---

## Why stub mode first

You could jump straight to building an LLM-powered agent. But that would mix two learning curves: LangGraph primitives (StateGraph, nodes, edges, reducers) and LLM integration (tool binding, ReAct loops, prompt engineering). When something breaks, you won't know which layer failed.

Stub mode separates the concerns. This session teaches:
- **TypedDict state** — the single shared state object that flows through the graph
- **Nodes as functions** — pure functions that receive state and return partial updates
- **Reducers** — how `Annotated[List[T], reducer_func]` controls merge behavior
- **Conditional edges** — routing based on state values
- **Compile and invoke** — turning a graph definition into a runnable

Session 07 will replace the stub classify node with an LLM + ToolNode ReAct loop. But the graph structure — the state schema, the node signatures, the edge topology — stays the same. Once you understand the structure in stub mode, adding the LLM is just swapping one node implementation for another.

---

## ClusterAgentState: the shared state schema

Every LangGraph graph has a state schema. For the cluster agent, that's `ClusterAgentState`, a TypedDict with 8 fields:

```python
class ClusterAgentState(TypedDict):
    cluster_id: str                                          # Which cluster this agent serves
    workflow_id: str                                         # Unique ID for this invocation
    sensor_events: Annotated[List[SensorEvent], append_events]  # Accumulating event window
    trigger_event: Optional[SensorEvent]                     # Most recent event
    messages: Annotated[List[BaseMessage], add_messages]     # LLM conversation (Session 07)
    anomalies: List[AnomalyFinding]                          # Detected findings
    status: Literal["idle", "processing", "complete", "error"]  # Workflow state
    error_message: Optional[str]                             # Error details if status=error
```

**Key insight:** This is the *only* data structure that flows through the graph. Every node receives the full state dict and returns a partial update. LangGraph merges the update into the current state and passes the merged state to the next node.

**Reducers:** Two fields use `Annotated` with a reducer function:

- `sensor_events: Annotated[List[SensorEvent], append_events]` — when a node returns `{"sensor_events": [new_event]}`, the `append_events` reducer *appends* the new event to the existing list instead of replacing it. This is how the event window accumulates across invocations.
  
- `messages: Annotated[List[BaseMessage], add_messages]` — same pattern for LLM messages. When the LLM node returns `{"messages": [ai_response]}`, it appends to the conversation history.

Without reducers, returning `{"sensor_events": [new]}` would *overwrite* the list with a single-element list. Reducers change the merge behavior.

---

## The three nodes

The cluster agent graph has three nodes in stub mode:

### 1. `ingest_events` — entry point

```python
def ingest_events(state: ClusterAgentState) -> dict:
    trigger = state.get("trigger_event")
    logger.info(
        "ClusterAgent[%s] ingesting event from source=%s",
        state.get("cluster_id"),
        trigger.source_id if trigger else "unknown",
    )
    return {
        "status": "processing",
        "error_message": None,
    }
```

This node:
- Logs the trigger event
- Sets `status` to `"processing"`
- Clears any previous error

**Partial update pattern:** The node returns only the two fields it changed. It doesn't return `cluster_id`, `sensor_events`, `messages`, etc. — those stay as-is. LangGraph merges `{"status": "processing", "error_message": None}` into the existing state.

### 2. `classify` — stub anomaly detection

```python
def classify(state: ClusterAgentState) -> dict:
    cluster_id = state.get("cluster_id", "unknown")
    trigger = state.get("trigger_event")
    
    stub_finding: AnomalyFinding = {
        "finding_id": str(uuid4()),
        "cluster_id": cluster_id,
        "anomaly_type": "stub_placeholder",
        "affected_sensors": [trigger.source_id] if trigger else [],
        "confidence": 0.5,
        "summary": f"[STUB] classify node not yet implemented for cluster {cluster_id}",
        "raw_context": {
            "trigger_event_id": trigger.event_id if trigger else None,
            "event_count_in_window": len(state.get("sensor_events", [])),
        },
    }
    
    return {
        "anomalies": [stub_finding],
        "status": "complete",
    }
```

This node:
- Creates a hardcoded `AnomalyFinding` with `anomaly_type="stub_placeholder"`
- Sets `status` to `"complete"`
- Returns the finding in the `anomalies` list

**AnomalyFinding structure:** Each finding is a TypedDict with:
- `finding_id` — UUID for deduplication
- `cluster_id` — which cluster detected this
- `anomaly_type` — classification (stub uses `"stub_placeholder"`, LLM will use `"threshold_breach"`, `"sensor_fault"`, etc.)
- `affected_sensors` — list of sensor IDs involved
- `confidence` — 0.0–1.0, how confident the agent is
- `summary` — human-readable explanation
- `raw_context` — dict with supporting data for the supervisor

Session 07 will replace this stub with an LLM that actually reasons about the sensor data. But the output structure stays the same.

### 3. `report_findings` — final node

```python
def report_findings(state: ClusterAgentState, store: Optional[BaseStore] = None) -> dict:
    anomalies = state.get("anomalies", [])
    cluster_id = state.get("cluster_id", "unknown")
    
    logger.info(
        "ClusterAgent[%s] reporting %d finding(s) to supervisor",
        cluster_id,
        len(anomalies),
    )
    
    if store is not None and anomalies:
        for finding in anomalies:
            store.put(
                ("incidents", cluster_id),
                finding["finding_id"],
                finding,
            )
    
    return {}
```

This node:
- Logs the findings count
- Writes each finding to the LangGraph Store (if provided) under namespace `("incidents", cluster_id)`
- Returns an empty dict (no state changes)

**Store integration:** The LangGraph Store is a key-value database for cross-agent memory. Cluster agents write findings here; the supervisor (Session 09) reads them to build context before making decisions. This is how agents share information across invocations without polluting the state dict.

The `store` parameter is injected by LangGraph when you compile with `builder.compile(store=store)`. Nodes that don't need it can omit the parameter.

---

## The graph topology

Here's the graph structure in stub mode:

```
START → ingest_events → classify → route_after_classify → report_findings → END
```

**Edges:**
- `START → ingest_events` — normal edge, always runs
- `ingest_events → classify` — normal edge, always runs
- `classify → route_after_classify` — **conditional edge**, router decides next node
- `route_after_classify → report_findings` — router returns `"report_findings"`
- `report_findings → END` — normal edge, graph terminates

**Conditional edge:** The router function inspects the state and returns the name of the next node:

```python
def route_after_classify(
    state: ClusterAgentState,
) -> Literal["report_findings", "__end__"]:
    if state.get("status") == "error":
        logger.warning(
            "ClusterAgent[%s] exiting due to error: %s",
            state.get("cluster_id"),
            state.get("error_message"),
        )
        return "__end__"
    
    return "report_findings"
```

In stub mode this always returns `"report_findings"` (unless there's an error). In LLM mode (Session 07), the router will check if the LLM wants to call tools and route to a `tool_node` instead, creating a loop.

---

## Building and compiling the graph

The `build_cluster_agent_graph()` function constructs the graph:

```python
def build_cluster_agent_graph(
    llm: Optional[BaseChatModel] = None,
    store: Optional[BaseStore] = None,
):
    builder = StateGraph(ClusterAgentState)
    
    builder.add_node("ingest_events", ingest_events)
    builder.add_node("report_findings", report_findings)
    
    builder.add_edge(START, "ingest_events")
    
    if llm is not None:
        # LLM mode (Session 07) — different topology
        ...
    else:
        # Stub mode
        builder.add_node("classify", classify)
        builder.add_edge("ingest_events", "classify")
        builder.add_conditional_edges("classify", route_after_classify)
    
    builder.add_edge("report_findings", END)
    
    compiled = builder.compile(store=store)
    return compiled
```

**StateGraph(ClusterAgentState):** The state schema is passed to the builder. LangGraph uses it to validate that nodes return compatible dicts.

**add_node(name, func):** Registers a node. The function must accept `state: ClusterAgentState` and return a dict.

**add_edge(from, to):** Normal edge — always follows this path.

**add_conditional_edges(from, router):** Conditional edge — calls the router function to decide the next node.

**compile():** Turns the builder into a runnable graph. After this, you can call `graph.invoke(state)` or `graph.stream(state)`.

---

## Running it

Here's a complete script that invokes the stub graph:

```python
from agents.cluster.graph import build_cluster_agent_graph
from transport.schemas import SensorEvent
from datetime import datetime, timezone

# Build the graph (stub mode, no LLM)
graph = build_cluster_agent_graph()

# Create a fake sensor event
event = SensorEvent.create(
    source_id="temp-1",
    source_type="temperature",
    cluster_id="cluster-north",
    payload={"celsius": 45.0, "unit": "C"},
    confidence=0.9,
    sim_tick=5,
)

# Invoke the graph
result = graph.invoke({
    "cluster_id": "cluster-north",
    "workflow_id": "test-run-1",
    "sensor_events": [event],
    "trigger_event": event,
    "messages": [],
    "anomalies": [],
    "status": "idle",
    "error_message": None,
})

# Inspect the result
print(f"Status: {result['status']}")
print(f"Findings: {len(result['anomalies'])}")
for f in result["anomalies"]:
    print(f"  [{f['anomaly_type']}] conf={f['confidence']:.2f}")
    print(f"  Summary: {f['summary']}")
    print(f"  Affected sensors: {f['affected_sensors']}")
```

You should see output like:

```
Status: complete
Findings: 1
  [stub_placeholder] conf=0.50
  Summary: [STUB] classify node not yet implemented for cluster cluster-north
  Affected sensors: ['temp-1']
```

The graph ran all three nodes:
1. `ingest_events` set `status="processing"`
2. `classify` created a stub finding and set `status="complete"`
3. `report_findings` logged the finding count

The result state contains the merged output of all nodes. The `anomalies` list has one finding. The `status` is `"complete"`.

---

## What you learned: LangGraph primitives

This session introduced the foundational LangGraph patterns:

**1. TypedDict state schema** — the single shared state object that flows through the graph. Every node receives it, every node returns a partial update.

**2. Reducers** — `Annotated[List[T], reducer_func]` changes how partial updates are merged. Without a reducer, returning `{"field": [new]}` overwrites. With `append_events`, it appends.

**3. Nodes as functions** — nodes are pure functions: `(state) → partial_update_dict`. They don't mutate state directly. They return what changed, and LangGraph merges it.

**4. Normal edges** — `add_edge(from, to)` always follows that path.

**5. Conditional edges** — `add_conditional_edges(from, router)` calls the router function to decide the next node based on state.

**6. Compile and invoke** — `builder.compile()` turns the graph definition into a runnable. `graph.invoke(state)` runs it and returns the final state.

These are the building blocks. Session 07 will add:
- **Tool binding** — `llm.bind_tools(tools)` attaches tool schemas to the LLM
- **ToolNode** — executes tool calls from the LLM's response
- **Cycles** — edges that loop back to earlier nodes (the ReAct loop)

But the state schema, the node signature pattern, and the edge topology stay the same. The stub graph you built here is the skeleton. Session 07 just swaps the classify node implementation.

---

## Key files

- `src/agents/cluster/state.py` — `ClusterAgentState` TypedDict, `AnomalyFinding` TypedDict, `append_events` reducer
- `src/agents/cluster/graph.py` — `build_cluster_agent_graph()`, node functions (`ingest_events`, `classify`, `report_findings`), routers (`route_after_classify`)

---

*Next: Session 07 replaces the stub classify node with an LLM-powered ReAct loop. The LLM will call tools to inspect sensor data, reason about anomalies, and produce findings based on actual analysis instead of hardcoded stubs. The graph topology changes to add a tool_node and a cycle, but the state schema and the other two nodes stay exactly the same.*
