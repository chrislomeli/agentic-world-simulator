"""
ogar.agents.supervisor

Supervisor agent graph — the top-level orchestrator.

Uses LangGraph's Send API to fan out to cluster agents, then
aggregates findings and decides on actions.

  - state.py  — SupervisorState TypedDict with aggregate reducer.
  - graph.py  — The StateGraph with Send-based fan-out pattern.

Pipeline:
  fan_out_to_clusters → run_cluster_agent (per cluster)
  → assess_situation → decide_actions → hitl_pause
  → dispatch_commands

The hitl_pause node uses a HumanApprovalGate (injected via
functools.partial) to gate destructive actions.
"""