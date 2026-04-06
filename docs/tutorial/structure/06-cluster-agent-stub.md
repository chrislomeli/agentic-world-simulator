# Session 06: Cluster Agent — Stub Mode

## Goal
Build a LangGraph StateGraph for the cluster agent using deterministic stub nodes. No LLM — just the graph primitives working end-to-end.

## Rubric Skills Introduced
| Skill | Level | Section |
|-------|-------|---------|
| StateGraph + TypedDict state | foundational | 1. Graph Primitives |
| Nodes — functions vs runnables | foundational | 1. Graph Primitives |
| Edges — normal vs conditional | foundational | 1. Graph Primitives |
| Reducers and Annotated state | mid-level | 1. Graph Primitives |
| Compile + invoke / stream | foundational | 1. Graph Primitives |

## Key Concepts
- **ClusterAgentState (TypedDict)** — the single shared state object
- **Annotated fields with reducers** — `sensor_events` uses `append_events` reducer, `messages` uses `add_messages`
- **Partial state updates** — nodes return only the fields they change
- **Conditional edges** — `route_after_classify` checks status to decide next node
- **Stub nodes** — `ingest_events` → `classify` (stub) → `report_findings`

## What You Build
1. Understand `ClusterAgentState` TypedDict with Annotated reducers
2. Build the graph: `ingest_events` → `classify` → `report_findings`
3. Add conditional edge after classify
4. Compile and invoke with hardcoded test data

## What You Can Run
```python
from agents.cluster.graph import build_cluster_agent_graph
from transport.schemas import SensorEvent

graph = build_cluster_agent_graph()  # stub mode, no LLM

# Create a fake sensor event
event = SensorEvent(
    event_id="test-001",
    source_id="temp-1",
    source_type="temperature",
    cluster_id="cluster-north",
    sim_tick=5,
    payload={"temperature_c": 45.0},
    confidence=0.9,
)

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

print(f"Status: {result['status']}")
print(f"Findings: {len(result['anomalies'])}")
for f in result["anomalies"]:
    print(f"  [{f['anomaly_type']}] {f['summary']}")
```

## Key Files
- `src/agents/cluster/state.py` — ClusterAgentState, AnomalyFinding, append_events reducer
- `src/agents/cluster/graph.py` — build_cluster_agent_graph(), node functions, routers

## LangGraph Patterns to Notice
1. **Reducers** — `sensor_events: Annotated[List[SensorEvent], append_events]` means returning `{"sensor_events": [new]}` appends, not overwrites
2. **Partial updates** — `ingest_events` returns `{"status": "processing"}` and nothing else; LangGraph merges it
3. **Conditional edges** — `route_after_classify` returns a node name string based on state

## Verification
- Graph compiles without errors
- invoke() runs all three nodes in order
- Result contains one stub finding with anomaly_type "stub_placeholder"
- Status transitions: idle → processing → complete

## Next Session
Session 07 replaces the stub classify with an LLM-powered ReAct loop.
