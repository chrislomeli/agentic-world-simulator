"""
ogar.agents.supervisor

Supervisor agent graph — owns the complete analysis workflow.

Uses LangGraph's Send API to fan out to cluster agents, then
correlates findings and decides on actions.

  - state.py  — SupervisorState TypedDict with aggregate reducer.
  - graph.py  — The StateGraph with Send-based fan-out pattern.
"""

from agents.supervisor.graph import build_supervisor_graph as build_supervisor_graph
from agents.supervisor.state import SupervisorState as SupervisorState
from agents.supervisor.state import aggregate_findings_reducer as aggregate_findings_reducer

__all__ = [
    "SupervisorState",
    "aggregate_findings_reducer",
    "build_supervisor_graph",
]
