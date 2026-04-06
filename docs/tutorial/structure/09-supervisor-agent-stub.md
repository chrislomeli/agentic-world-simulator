# Session 09: Supervisor Agent — Stub Mode

## Goal
Build the supervisor agent that fans out to cluster agents via the Send API, aggregates their findings with a custom reducer, and produces ActuatorCommands. Stub mode — no LLM.

## Rubric Skills Introduced
| Skill | Level | Section |
|-------|-------|---------|
| Parallel node execution (Send API) | mid-level | 2. Control Flow |
| Subgraphs — compile and invoke | mid-level | 5. Multi-Agent |
| State schema handoff between graphs | mid-level | 5. Multi-Agent |
| Supervisor pattern | mid-level | 5. Multi-Agent |
| Reducers and Annotated state | mid-level | 1. Graph Primitives |

## Key Concepts
- **Send API** — `fan_out_to_clusters` returns `List[Send]`; LangGraph runs them in parallel
- **Dynamic fan-out** — number of cluster agents is determined at runtime from state
- **Custom reducer** — `aggregate_findings_reducer` merges findings from parallel agents, deduplicating by finding_id
- **Subgraph invocation** — `run_cluster_agent` calls `cluster_agent_graph.invoke(state)` synchronously
- **State schema handoff** — SupervisorState ≠ ClusterAgentState; explicit mapping between them
- **ActuatorCommand** — structured output that the supervisor produces

## Graph Topology (Stub mode)
```
START ──→ fan_out_to_clusters (conditional edge returning Send objects)
              ↓
          run_cluster_agent (×N, parallel)
              ↓
          assess_situation (stub)
              ↓
          decide_actions (stub)
              ↓
          dispatch_commands → END
```

## What You Build
1. Understand `SupervisorState` with `aggregate_findings_reducer`
2. See how `fan_out_to_clusters` returns `List[Send]`
3. See how `run_cluster_agent` wraps the cluster subgraph
4. Invoke the supervisor with hardcoded findings

## What You Can Run
```python
from agents.supervisor.graph import build_supervisor_graph

graph = build_supervisor_graph()  # stub mode

result = graph.invoke({
    "active_cluster_ids": ["cluster-north", "cluster-south"],
    "cluster_findings": [],
    "messages": [],
    "pending_commands": [],
    "situation_summary": None,
    "status": "idle",
})

print(f"Status: {result['status']}")
print(f"Findings aggregated: {len(result['cluster_findings'])}")
print(f"Summary: {result['situation_summary']}")
print(f"Commands: {len(result['pending_commands'])}")
```

## Key Files
- `src/agents/supervisor/state.py` — SupervisorState, aggregate_findings_reducer
- `src/agents/supervisor/graph.py` — build_supervisor_graph(), fan_out_to_clusters, run_cluster_agent
- `src/actuators/base.py` — ActuatorCommand

## LangGraph Patterns to Notice
1. **Send API** — `fan_out_to_clusters` is wired as a conditional edge from START, not a regular node. It returns `[Send("run_cluster_agent", state)]` for each cluster.
2. **Custom reducer** — `cluster_findings: Annotated[List[AnomalyFinding], aggregate_findings_reducer]` — merges findings from parallel Send targets
3. **Subgraph isolation** — each `run_cluster_agent` invocation has completely isolated state
4. **State mapping** — supervisor constructs ClusterAgentState from its own state fields

## Verification
- Fan-out creates one Send per active cluster
- Cluster agent subgraphs run (producing stub findings)
- Findings are aggregated via the custom reducer
- assess_situation produces a summary string
- Status reaches "complete"

## Next Session
Session 10 replaces stub nodes with LLM-powered assess and decide loops.
