# Episode 3, Session 9: The Supervisor Agent (Stub Mode)

> **What we're building:** A supervisor agent that coordinates multiple cluster agents using the Send API, aggregates their findings, and produces action decisions.
> **Why we need it:** Sessions 06–08 built cluster agents that work independently. This session adds the supervisor layer — the agent that sees the big picture across all clusters, correlates findings, and decides what actions to take. This is the multi-agent coordination pattern.
> **What you'll have at the end:** A supervisor graph that fans out to N cluster agents in parallel, merges their findings with a custom reducer, and produces a situation summary — all with deterministic stub logic before adding the LLM in Session 10.

---

## Why a supervisor matters

Sessions 06–08 gave you cluster agents. Each cluster agent sees sensor events from its own cluster and produces findings: "temperature spike in cluster-north", "smoke detected in cluster-south". But cluster agents don't talk to each other. They don't know what's happening in other clusters.

The supervisor solves this. It:
1. **Coordinates** — invokes all cluster agents in parallel when significant events occur
2. **Aggregates** — collects findings from all clusters into a single view
3. **Correlates** — looks for patterns across clusters (same anomaly in multiple places)
4. **Decides** — produces actuator commands based on the overall situation

This is the **supervisor pattern** in multi-agent systems. Cluster agents are specialists (local experts). The supervisor is the generalist (global coordinator). The supervisor doesn't replace cluster agents — it orchestrates them.

---

## SupervisorState: the outer state schema

The supervisor has its own state schema, separate from `ClusterAgentState`:

```python
class SupervisorState(TypedDict):
    active_cluster_ids: List[str]                                    # Which clusters to fan out to
    cluster_findings: Annotated[List[AnomalyFinding], aggregate_findings_reducer]  # Aggregated results
    messages: Annotated[List[BaseMessage], add_messages]             # LLM conversation (Session 10)
    pending_commands: List[ActuatorCommand]                          # Actions to dispatch
    situation_summary: Optional[str]                                 # Human-readable assessment
    status: Literal["idle", "aggregating", "assessing", "deciding", "dispatching", "complete", "error"]
    error_message: Optional[str]
```

**Key differences from ClusterAgentState:**
- No `sensor_events` — the supervisor doesn't see raw sensor data
- No `trigger_event` — the supervisor is triggered by cluster findings, not sensor events
- Has `active_cluster_ids` — the list of clusters to coordinate
- Has `cluster_findings` with a custom reducer — this is where parallel results merge
- Has `pending_commands` — the supervisor's output (cluster agents produce findings, supervisor produces commands)

**The custom reducer:**

```python
def aggregate_findings_reducer(
    existing: List[AnomalyFinding],
    incoming: List[AnomalyFinding],
) -> List[AnomalyFinding]:
    existing_ids = {f["finding_id"] for f in existing}
    new_findings = [f for f in incoming if f["finding_id"] not in existing_ids]
    return existing + new_findings
```

When cluster agents run in parallel via the Send API, each returns a list of findings. The reducer merges them into `cluster_findings`, deduplicating by `finding_id`. This is how parallel results accumulate into the supervisor's state.

---

## The Send API: dynamic fan-out

The Send API is LangGraph's pattern for dynamic parallel execution. Here's how it works:

**1. A function returns `List[Send]` instead of a state dict:**

```python
def fan_out_to_clusters(state: SupervisorState) -> List[Send]:
    cluster_ids = state.get("active_cluster_ids", [])
    sends = []
    for cluster_id in cluster_ids:
        cluster_state: ClusterAgentState = {
            "cluster_id": cluster_id,
            "workflow_id": f"{cluster_id}::supervisor-fanout",
            "sensor_events": [],
            "trigger_event": None,
            "messages": [],
            "anomalies": [],
            "status": "idle",
            "error_message": None,
        }
        sends.append(Send("run_cluster_agent", cluster_state))
    return sends
```

Each `Send("run_cluster_agent", cluster_state)` is an instruction: "invoke the `run_cluster_agent` node with this state as input".

**2. LangGraph runs all Send targets in parallel:**

If `active_cluster_ids = ["cluster-north", "cluster-south"]`, the function returns 2 Send objects. LangGraph invokes `run_cluster_agent` twice in parallel, once with `cluster_id="cluster-north"` and once with `cluster_id="cluster-south"`.

**3. Results merge via the reducer:**

Each `run_cluster_agent` invocation returns `{"cluster_findings": [finding1, finding2, ...]}`. The `aggregate_findings_reducer` merges all the lists into the supervisor's `cluster_findings` field.

**Why this matters:** The number of cluster agents is determined at runtime from `active_cluster_ids`. If you have 1 cluster, 1 agent runs. If you have 10 clusters, 10 agents run in parallel. No code changes. This is dynamic fan-out.

---

## State schema handoff: SupervisorState → ClusterAgentState

The supervisor and cluster agents have different state schemas. The supervisor constructs a `ClusterAgentState` dict for each Send:

```python
cluster_state: ClusterAgentState = {
    "cluster_id": cluster_id,                    # From supervisor's active_cluster_ids
    "workflow_id": f"{cluster_id}::supervisor-fanout",
    "sensor_events": [],                         # Empty — supervisor doesn't have sensor data
    "trigger_event": None,                       # No specific trigger
    "messages": [],                              # Fresh conversation
    "anomalies": [],                             # Will be populated by cluster agent
    "status": "idle",
    "error_message": None,
}
```

This is **state mapping** — translating between two different state schemas. The supervisor knows what the cluster agent needs (a `ClusterAgentState` dict) and constructs it from its own state.

When the cluster agent finishes, it returns a state dict with `anomalies` populated. The `run_cluster_agent` wrapper extracts `anomalies` and maps it to the supervisor's `cluster_findings`:

```python
def run_cluster_agent(state: ClusterAgentState) -> dict:
    result_state = cluster_agent_graph.invoke(state)
    return {
        "cluster_findings": result_state.get("anomalies", []),
    }
```

The supervisor never sees the cluster agent's `messages` or `sensor_events`. It only gets the findings.

---

## The graph topology (stub mode)

Here's the supervisor graph structure in stub mode:

```
START → fan_out_to_clusters (conditional edge)
            ↓
        run_cluster_agent (×N, parallel)
            ↓
        assess_situation (stub)
            ↓
        decide_actions (stub)
            ↓
        route_after_decide (conditional edge)
            ↓
        dispatch_commands → END
```

**Edges:**
- `START → fan_out_to_clusters` — **conditional edge**, returns `List[Send]`
- `fan_out_to_clusters → run_cluster_agent` — LangGraph interprets the Send objects as parallel invocations
- `run_cluster_agent → assess_situation` — normal edge, runs after all parallel invocations complete
- `assess_situation → decide_actions` — normal edge
- `decide_actions → route_after_decide` — conditional edge, checks for errors
- `route_after_decide → dispatch_commands` — router returns `"dispatch_commands"`
- `dispatch_commands → END` — normal edge

**Key insight:** `fan_out_to_clusters` is wired as a conditional edge from START, not a regular node. It's a routing function that returns Send objects instead of a state dict. This is how you tell LangGraph "run these nodes in parallel".

---

## The stub nodes

### 1. `assess_situation` — stub summary

```python
def assess_situation(state: SupervisorState, store: Optional[BaseStore] = None) -> dict:
    findings = state.get("cluster_findings", [])
    cluster_ids = state.get("active_cluster_ids", [])
    
    past_count = 0
    if store is not None:
        for cid in cluster_ids:
            items = store.search(("incidents", cid))
            past_count += len(items)
    
    summary = (
        f"[STUB] Received {len(findings)} finding(s) from "
        f"{len(cluster_ids)} cluster(s). "
        f"Store contains {past_count} past incident(s) across all clusters."
    )
    
    return {
        "situation_summary": summary,
        "status": "deciding",
        "messages": [AIMessage(content=summary)],
    }
```

This stub:
- Counts findings and clusters
- Reads past incidents from the LangGraph Store (if provided) to include historical context
- Produces a hardcoded summary string
- Sets `status="deciding"` to move to the next phase

Session 10 will replace this with an LLM that actually reasons about the findings.

### 2. `decide_actions` — stub (no commands)

```python
def decide_actions(state: SupervisorState) -> dict:
    return {
        "pending_commands": [],
        "status": "dispatching",
    }
```

The stub produces no commands. Session 10 will replace this with an LLM that decides what actuator commands to issue based on the situation summary.

### 3. `dispatch_commands` — write to Store

```python
def dispatch_commands(state: SupervisorState, store: Optional[BaseStore] = None) -> dict:
    commands = state.get("pending_commands", [])
    summary = state.get("situation_summary", "")
    
    if store is not None and summary:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        store.put(
            ("situations", "global"),
            ts,
            {
                "situation_summary": summary,
                "command_count": len(commands),
                "command_types": [c.command_type for c in commands],
            },
        )
    
    return {"status": "complete"}
```

This node:
- Logs the command count
- Writes the situation summary to the Store under namespace `("situations", "global")` with a timestamp key
- Sets `status="complete"`

The Store write gives the supervisor memory across invocations. Future runs can read past situations to avoid duplicate alerts or to reason about escalation patterns.

---

## Running it

Here's a complete script that invokes the supervisor in stub mode:

```python
from agents.supervisor.graph import build_supervisor_graph

# Build the graph (stub mode, no LLM)
graph = build_supervisor_graph()

# Invoke with 2 active clusters
result = graph.invoke({
    "active_cluster_ids": ["cluster-north", "cluster-south"],
    "cluster_findings": [],
    "messages": [],
    "pending_commands": [],
    "situation_summary": None,
    "status": "idle",
    "error_message": None,
})

# Inspect the result
print(f"Status: {result['status']}")
print(f"Findings aggregated: {len(result['cluster_findings'])}")
print(f"Summary: {result['situation_summary']}")
print(f"Commands: {len(result['pending_commands'])}")

# Inspect individual findings
for i, f in enumerate(result["cluster_findings"], 1):
    print(f"\n{i}. [{f['anomaly_type']}] cluster={f['cluster_id']} conf={f['confidence']:.2f}")
    print(f"   Summary: {f['summary'][:80]}")
```

**Expected output (stub mode):**

```
Status: complete
Findings aggregated: 2
Summary: [STUB] Received 2 finding(s) from 2 cluster(s). Store contains 0 past incident(s) across all clusters.
Commands: 0

1. [stub_placeholder] cluster=cluster-north conf=0.50
   Summary: [STUB] classify node not yet implemented for cluster cluster-north

2. [stub_placeholder] cluster=cluster-south conf=0.50
   Summary: [STUB] classify node not yet implemented for cluster cluster-south
```

The supervisor:
1. Fanned out to 2 clusters in parallel
2. Each cluster agent ran and produced 1 stub finding
3. The reducer merged both findings into `cluster_findings`
4. `assess_situation` produced a summary counting the findings
5. `decide_actions` produced no commands (stub)
6. Status reached `"complete"`

---

## What you learned: Multi-agent coordination

This session introduced the multi-agent patterns:

**1. Send API** — a function returns `List[Send]` to trigger parallel node invocations. Each Send specifies a target node and an input state.

**2. Dynamic fan-out** — the number of parallel invocations is determined at runtime from state. Add a cluster to `active_cluster_ids`, and the supervisor automatically invokes its agent.

**3. Custom reducer** — `aggregate_findings_reducer` merges results from parallel Send targets, deduplicating by `finding_id`.

**4. State schema handoff** — the supervisor constructs `ClusterAgentState` dicts for each cluster agent, mapping between two different state schemas.

**5. Subgraph invocation** — `cluster_agent_graph.invoke(state)` runs the cluster agent as a synchronous call. The cluster agent's internal state is completely isolated from the supervisor's state.

**6. Store integration** — the supervisor reads past incidents from `("incidents", cluster_id)` and writes situation summaries to `("situations", "global")` for cross-invocation memory.

The supervisor doesn't replace cluster agents. It coordinates them. Cluster agents are still responsible for classifying sensor events. The supervisor is responsible for seeing the big picture and deciding what to do about it.

---

## Key files

- `src/agents/supervisor/state.py` — `SupervisorState` TypedDict, `aggregate_findings_reducer`
- `src/agents/supervisor/graph.py` — `build_supervisor_graph()`, `fan_out_to_clusters`, `run_cluster_agent`, stub nodes
- `src/actuators/base.py` — `ActuatorCommand` (the supervisor's output format)

---

*Next: Session 10 replaces the stub assess and decide nodes with LLM-powered ReAct loops. The supervisor will use tools to examine findings, correlate across clusters, and produce reasoned actuator commands. The graph topology changes to add two separate tool loops (assess and decide), but the Send API fan-out and the reducer stay exactly the same.*
