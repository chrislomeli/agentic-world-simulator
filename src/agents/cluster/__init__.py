"""
ogar.agents.cluster

Cluster-level agent graph.

Processes sensor events for a single geographic cluster.
Pipeline: ingest_events → classify → route → report_findings.

  - state.py  — ClusterAgentState TypedDict + AnomalyFinding model.
  - graph.py  — The compiled LangGraph StateGraph.
"""

from agents.cluster.graph import build_cluster_agent_graph as build_cluster_agent_graph
from agents.cluster.state import AnomalyFinding as AnomalyFinding
from agents.cluster.state import ClusterAgentState as ClusterAgentState
from agents.cluster.state import append_events as append_events

__all__ = [
    "AnomalyFinding",
    "ClusterAgentState",
    "append_events",
    "build_cluster_agent_graph",
]
