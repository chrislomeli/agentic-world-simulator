# Session 10: Supervisor Agent — LLM Mode

## Goal
Replace stub assess and decide nodes with two separate LLM ReAct loops. The supervisor now uses tools to examine findings, correlate across clusters, and produce reasoned ActuatorCommands.

## Rubric Skills Introduced
| Skill | Level | Section |
|-------|-------|---------|
| Cycles / loops | mid-level | 2. Control Flow |
| Dynamic branching | mid-level | 2. Control Flow |
| Structured output tools | mid-level | 3. Tools |

## Key Concepts
- **Two ReAct loops** — assess and decide each have their own LLM ↔ ToolNode cycle
- **Tool composition** — supervisor tools (4) + resource tools (4) = 8 tools bound to one LLM
- **Node factories** — `_make_assess_llm_node()` and `_make_decide_llm_node()` return closures
- **Structured output** — LLM must produce valid JSON for ActuatorCommand creation
- **System prompt engineering** — separate prompts for assess vs. decide phases

## Graph Topology (LLM mode)
```
START → fan_out_to_clusters → run_cluster_agent (×N)
     → assess_situation_llm ──→ parse_assessment
             ↓    ↑                    ↓
        assess_tool_node         decide_actions_llm ──→ parse_commands
                                      ↓    ↑                  ↓
                                 decide_tool_node      dispatch_commands → END
```

## What You Build
1. See how `_make_assess_llm_node` builds system prompt with cluster context
2. See how the assess loop uses supervisor tools to examine findings
3. See how `_parse_assessment` extracts JSON from LLM response
4. See the decide loop producing ActuatorCommands
5. Run with an actual LLM

## What You Can Run
```python
from langchain_openai import ChatOpenAI
from agents.supervisor.graph import build_supervisor_graph

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
graph = build_supervisor_graph(llm=llm)

result = graph.invoke({
    "active_cluster_ids": ["cluster-north", "cluster-south"],
    "cluster_findings": [],
    "messages": [],
    "pending_commands": [],
    "situation_summary": None,
    "status": "idle",
})

print(f"Summary: {result['situation_summary']}")
print(f"Commands: {len(result['pending_commands'])}")
for cmd in result["pending_commands"]:
    print(f"  [{cmd.command_type}] → {cmd.cluster_id} (priority={cmd.priority})")
```

## Key Files
- `src/agents/supervisor/graph.py` — _make_assess_llm_node, _make_decide_llm_node, route_after_assess_llm, route_after_decide_llm
- `src/tools/supervisor_tools.py` — 4 supervisor tools + _SupervisorToolState

## LangGraph Patterns to Notice
1. **Two separate cycles** — assess and decide are independent ReAct loops with different system prompts
2. **Tool state management** — `set_supervisor_tool_state()` before each LLM call, `clear_supervisor_tool_state()` after
3. **Parse nodes** — `_parse_assessment` and `_parse_commands` handle LLM output parsing with fallbacks
4. **Conditional edges** — `route_after_assess_llm` checks for tool_calls; routes to tool_node or parse_assessment

## Verification
- LLM calls supervisor tools during assessment
- Situation summary reflects actual finding analysis
- ActuatorCommands have valid command_type and payload
- Compare stub output (Session 09) to LLM output for same findings

## Next Session
Session 11 introduces resources — preparedness assets on the grid.
