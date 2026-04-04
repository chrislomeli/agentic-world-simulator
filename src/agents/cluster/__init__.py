"""
ogar.agents.cluster

Cluster-level agent graph.

Processes sensor events for a single geographic cluster.
Pipeline: ingest_events → classify → route → report_findings.

  - state.py  — ClusterAgentState TypedDict + AnomalyFinding model.
  - graph.py  — The compiled LangGraph StateGraph.

The classify node is currently a STUB — it produces placeholder
AnomalyFinding entries.  Next step: wire in ToolNode + LLM calls
for real anomaly detection.
"""