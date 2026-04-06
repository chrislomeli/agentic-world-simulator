# Session 07: Cluster Agent — LLM Mode

## Goal
Replace the stub classify node with an LLM-powered ReAct loop: LLM reasons, calls tools, gets results, reasons again, produces a finding.

## Rubric Skills Introduced
| Skill | Level | Section |
|-------|-------|---------|
| Tool definition — @tool decorator | foundational | 3. Tools |
| ToolNode + bind_tools | foundational | 3. Tools |
| Cycles / loops | mid-level | 2. Control Flow |
| Dynamic branching | mid-level | 2. Control Flow |

## Key Concepts
- **@tool decorator** — docstring → tool description, type hints → schema; LLM sees both
- **bind_tools()** — attaches tool schemas to the LLM so it can produce tool_calls
- **ToolNode** — executes tool calls from AIMessage, returns ToolMessage results
- **ReAct loop** — classify_llm → (tool_calls?) → tool_node → classify_llm → ... → parse_findings
- **Conditional edge** — `route_after_classify_llm` checks for tool_calls to decide loop vs. exit

## What You Build
1. Understand the 4 sensor tools in `sensor_tools.py`
2. See how `_make_classify_llm_node` builds the LLM node with tools
3. See the ReAct loop: classify_llm ↔ tool_node cycle
4. Run with an actual LLM (requires API key)

## Graph Topology (LLM mode)
```
START → ingest_events → classify_llm ──→ parse_findings → report_findings → END
                            ↓    ↑
                        tool_node
```

The cycle between `classify_llm` and `tool_node` is the ReAct loop. The LLM calls tools until it's satisfied, then produces a final text response.

## What You Can Run
```python
from langchain_openai import ChatOpenAI
from agents.cluster.graph import build_cluster_agent_graph

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
graph = build_cluster_agent_graph(llm=llm)

# Same invocation as Session 06 — different graph topology
result = graph.invoke({
    "cluster_id": "cluster-north",
    "workflow_id": "test-llm-1",
    "sensor_events": [event],
    "trigger_event": event,
    "messages": [],
    "anomalies": [],
    "status": "idle",
    "error_message": None,
})

# Now the finding comes from LLM reasoning, not a stub
for f in result["anomalies"]:
    print(f"  [{f['anomaly_type']}] conf={f['confidence']:.2f} {f['summary']}")
```

## Key Files
- `src/tools/sensor_tools.py` — 4 @tool functions: get_recent_readings, get_sensor_summary, check_threshold, get_cluster_status
- `src/agents/cluster/graph.py` — _make_classify_llm_node, route_after_classify_llm, _parse_llm_findings

## LangGraph Patterns to Notice
1. **Tool definition** — `@tool` + docstring + type hints = complete tool schema
2. **Module-level state holder** — tools read sensor events from `_state` set before LLM call
3. **Cycle** — tool_node edge goes BACK to classify_llm (not forward). This is a loop.
4. **Termination** — loop exits when LLM stops producing tool_calls

## Verification
- LLM calls at least one tool before producing final answer
- Final response is parsed into an AnomalyFinding
- Confidence and anomaly_type reflect LLM's actual analysis
- Compare stub output (Session 06) to LLM output for same input

## Next Session
Session 08 wires the full sensor → agent pipeline end-to-end.
