"""
ogar.agents.supervisor.state

State schema for the supervisor agent LangGraph graph.

What is the supervisor?
────────────────────────
The supervisor owns the complete analysis workflow for a batch of
triggered locations:

  1. Receives a batch of events grouped by cluster/location.
  2. Fans out to cluster agents via the Send API (parallel analysis).
  3. Waits for ALL cluster agents to complete (synchronization barrier).
  4. Correlates findings across clusters (is this one fire or many?).
  5. Decides which actuator commands to issue.
  6. Dispatches commands to actuators.

The Send API pattern
────────────────────
fan_out_to_clusters returns a list of Send() objects — one per cluster.
LangGraph runs all cluster agents in parallel and waits for all to
complete before advancing to assess_situation.  This is the
synchronization barrier — the supervisor needs the complete picture
before correlating.

Reducers
────────
aggregate_findings_reducer: AnomalyFindings accumulate as cluster
  agents report in.  The supervisor never overwrites past findings
  within a single execution.

messages: Standard add_messages from LangGraph — appends, never overwrites.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from actuators.base import ActuatorCommand
from agents.cluster.state import AnomalyFinding

# ── Custom reducer for aggregating cluster findings ───────────────────────────

def aggregate_findings_reducer(
    existing: list[AnomalyFinding],
    incoming: list[AnomalyFinding],
) -> list[AnomalyFinding]:
    """
    Accumulate findings from cluster agents.

    When the Send API fan-out completes, each cluster agent's findings
    come back as a separate incoming list.  This reducer merges them
    into a single accumulated list on the supervisor state.

    Deduplication by finding_id prevents double-counting if a cluster
    agent is somehow invoked twice for the same event.
    """
    existing_ids = {f["finding_id"] for f in existing}
    new_findings = [f for f in incoming if f["finding_id"] not in existing_ids]
    return existing + new_findings


# ── Supervisor state ──────────────────────────────────────────────────────────

class SupervisorState(TypedDict):
    """
    The working state for a single supervisor graph execution.

    One execution is triggered each time the event loop (or orchestrator)
    delivers a batch of events from triggered locations.
    """

    # ── Input ─────────────────────────────────────────────────────────
    # Which clusters/locations have active events in this batch.
    # The supervisor fans out to ALL of these via Send API.
    active_cluster_ids: list[str]

    # Events grouped by cluster/location.  Passed in by the caller
    # (event loop's on_batch or supervisor_runner).
    # fan_out_to_clusters reads this to populate each cluster agent's
    # sensor_events before invoking it.
    events_by_cluster: dict[str, list[Any]]

    # ── Aggregated findings (output of cluster agent fan-out) ─────────
    # Populated by cluster agents via Send API fan-out.
    # aggregate_findings_reducer merges results from each cluster agent
    # after the synchronization barrier.
    cluster_findings: Annotated[list[AnomalyFinding], aggregate_findings_reducer]

    # ── LLM reasoning ────────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Decision output ───────────────────────────────────────────────
    pending_commands: list[ActuatorCommand]

    # ── Situation summary ─────────────────────────────────────────────
    situation_summary: str | None

    # ── Control ───────────────────────────────────────────────────────
    status: Literal[
        "idle",
        "aggregating",      # Waiting for cluster agents (Send API fan-out)
        "assessing",        # Correlating cross-cluster findings
        "deciding",         # Choosing actions
        "dispatching",      # Sending commands to actuators
        "complete",
        "error",
    ]

    error_message: str | None
