"""
ogar.agents

LangGraph agent graphs.

This package contains the agent graphs that process sensor data,
detect anomalies, and decide on actions.  The architecture is
hierarchical:

  - cluster/   — ClusterAgent: processes sensor events for one
                 geographic cluster, detects anomalies.
  - supervisor/ — SupervisorAgent: fans out to cluster agents
                  via LangGraph's Send API, aggregates findings,
                  decides actions, gates through HITL approval.

Each agent is a compiled LangGraph StateGraph.  The supervisor
invokes cluster agents as subgraphs.
"""