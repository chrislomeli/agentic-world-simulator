"""
ogar.agents.supervisor.state

State schema for the supervisor agent LangGraph graph.

What is the supervisor?
────────────────────────
The supervisor is the top-level agent.  It:
  1. Receives findings from cluster agents (via Send API fan-out).
  2. Correlates findings across clusters.
  3. Decides which actuator commands to issue.
  4. Dispatches commands to actuators (including async notifications).

State design
────────────
The supervisor state is the "outer" state.
When the supervisor invokes cluster agent subgraphs via Send API,
each cluster agent has its own internal ClusterAgentState.
The supervisor maps results from ClusterAgentState back into
SupervisorState after each cluster agent finishes.

The key LangGraph pattern here is the Send API:
  - supervisor creates one Send() per cluster for fan-out
  - each Send() passes a ClusterAgentState-shaped dict to the subgraph
  - results come back as a list and get merged into SupervisorState
    via the aggregate_findings_reducer

Reducers
────────
aggregate_findings_reducer: AnomalyFindings accumulate as cluster
  agents report in.  The supervisor never overwrites past findings
  within a single execution.

messages: Standard add_messages from LangGraph — appends, never overwrites.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from ogar.actuators.base import ActuatorCommand
from ogar.agents.cluster.state import AnomalyFinding


# ── Custom reducer for aggregating cluster findings ───────────────────────────

def aggregate_findings_reducer(
    existing: List[AnomalyFinding],
    incoming: List[AnomalyFinding],
) -> List[AnomalyFinding]:
    """
    Accumulate findings from cluster agents.

    When the Send API fan-out completes, each cluster agent's findings
    come back as a separate incoming list.  This reducer merges them
    into a single accumulated list on the supervisor state.

    Deduplication by finding_id prevents double-counting if a cluster
    agent is somehow invoked twice for the same event.
    """
    # Build a set of already-seen finding IDs to prevent duplicates.
    existing_ids = {f["finding_id"] for f in existing}
    new_findings = [f for f in incoming if f["finding_id"] not in existing_ids]
    return existing + new_findings


# ── Supervisor state ──────────────────────────────────────────────────────────

class SupervisorState(TypedDict):
    """
    The working state for a single supervisor agent execution.

    One supervisor execution is triggered each time a significant
    cluster finding warrants cross-cluster correlation and action.
    """

    # ── Trigger context ───────────────────────────────────────────────
    # Which clusters have active events that triggered this run.
    # The supervisor fans out to ALL of these via Send API.
    active_cluster_ids: List[str]

    # ── Aggregated findings ───────────────────────────────────────────
    # Populated by cluster agents via Send API fan-out.
    # aggregate_findings_reducer merges results from each cluster.
    cluster_findings: Annotated[List[AnomalyFinding], aggregate_findings_reducer]

    # ── LLM reasoning ────────────────────────────────────────────────
    # The supervisor's own tool loop for cross-cluster correlation.
    messages: Annotated[List[BaseMessage], add_messages]

    # ── Decision output ───────────────────────────────────────────────
    # Commands the supervisor decides to issue after assessing findings.
    # Set by decide_actions node, consumed by dispatch_commands node.
    pending_commands: List[ActuatorCommand]

    # ── Situation summary ─────────────────────────────────────────────
    # Human-readable summary of what the supervisor determined.
    # Written by assess_situation, used in notifications and audit log.
    situation_summary: Optional[str]

    # ── Control ───────────────────────────────────────────────────────
    status: Literal[
        "idle",
        "aggregating",      # Waiting for cluster agents to report in
        "assessing",        # LLM correlating cross-cluster findings
        "deciding",         # Choosing actions
        "dispatching",      # Sending commands to actuators
        "complete",
        "error",
    ]

    error_message: Optional[str]
