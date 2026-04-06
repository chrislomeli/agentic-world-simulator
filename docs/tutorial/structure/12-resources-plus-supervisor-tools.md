# Session 12: Resources + Supervisor Tools

## Goal
Wire the 4 resource tools into the supervisor's LLM tool set so it can query preparedness during assessment and decision-making.

## Rubric Skills Introduced
| Skill | Level | Section |
|-------|-------|---------|
| Tool definition — @tool decorator | foundational | 3. Tools |

## Key Concepts
- **Resource tools** — 4 @tool functions: get_resource_summary, get_resources_by_cluster, get_resources_by_type, check_preparedness
- **Combined tool binding** — `SUPERVISOR_TOOLS + RESOURCE_TOOLS` bound to one LLM
- **Shared state holder** — resource tools read from the same `_SupervisorToolState` as supervisor tools
- **Optional integration** — `resource_inventory=None` means no resource tools (backward compatible)

## What You Build
1. Understand the 4 resource tools in `resource_tools.py`
2. See how `build_supervisor_graph(resource_inventory=...)` combines tool sets
3. See how `set_supervisor_tool_state()` loads the inventory for tools
4. Run supervisor with resources and observe LLM querying preparedness

## What You Can Run
```python
from langchain_openai import ChatOpenAI
from agents.supervisor.graph import build_supervisor_graph
from domains.wildfire import create_full_wildfire_scenario

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
engine, resources = create_full_wildfire_scenario()

# Supervisor now has 8 tools (4 supervisor + 4 resource)
graph = build_supervisor_graph(llm=llm, resource_inventory=resources)

result = graph.invoke({
    "active_cluster_ids": ["cluster-north", "cluster-south"],
    "cluster_findings": [],
    "messages": [],
    "pending_commands": [],
    "situation_summary": None,
    "status": "idle",
})

# LLM should mention resource availability in its summary
print(f"Summary: {result['situation_summary']}")
```

**Test resource tools in isolation:**
```python
from tools.resource_tools import (
    set_resource_tool_state, clear_resource_tool_state,
    get_resource_summary, check_preparedness,
)
from domains.wildfire import create_wildfire_resources

resources = create_wildfire_resources()
set_resource_tool_state(resources)

print(get_resource_summary.invoke({}))
print(check_preparedness.invoke({"cluster_id": "cluster-south"}))

clear_resource_tool_state()
```

## Key Files
- `src/tools/resource_tools.py` — 4 resource tools, RESOURCE_TOOLS list
- `src/agents/supervisor/graph.py` — combined tool binding logic (lines 628–646)
- `src/tools/supervisor_tools.py` — _SupervisorToolState (shared by both tool sets)

## LangGraph Patterns to Notice
1. **Additive tool composition** — `all_tools = SUPERVISOR_TOOLS + RESOURCE_TOOLS` when inventory is present
2. **Same ToolNode for both** — `ToolNode(all_tools)` handles both supervisor and resource tool calls
3. **Backward compatibility** — `resource_inventory=None` means only 4 supervisor tools are bound

## Verification
- With resources: LLM has 8 tools available
- Without resources: LLM has 4 tools (no resource tools)
- check_preparedness returns gap analysis with capacity info
- get_resource_summary matches inventory.readiness_summary()

## Next Session
Session 13 wires everything together into a complete pipeline.
