"""
ogar.agents.cluster.graph

Cluster agent LangGraph subgraph — supports both stub and LLM modes.

Topology (stub mode — no LLM):
  START → ingest_events → classify_stub → route_after_classify
        → report_findings → END

Topology (LLM mode — with tools):
  START → ingest_events → classify_llm → route_after_classify
        → [tool_calls] → tool_node → classify_llm
        → [done]       → report_findings → END

Usage:
  # Stub mode (default — no API key needed):
  graph = build_cluster_agent_graph()

  # LLM mode:
  from langchain_openai import ChatOpenAI
  llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
  graph = build_cluster_agent_graph(llm=llm)

Why a subgraph?
───────────────
The cluster agent is compiled as a standalone subgraph.
The supervisor invokes it as a node (via Send API fan-out).
Each invocation gets its own state, which is why it can run in
parallel for multiple clusters without state collision.

Compiling separately also means it can be tested in isolation —
you can invoke the cluster agent directly with a SensorEvent
without needing the supervisor running.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Optional
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from ogar.agents.cluster.state import AnomalyFinding, ClusterAgentState
from ogar.tools.sensor_tools import SENSOR_TOOLS, clear_tool_state, set_tool_state

logger = logging.getLogger(__name__)


# ── System prompt for classify LLM ───────────────────────────────────────────

CLASSIFY_SYSTEM_PROMPT = """You are a wildfire monitoring analyst for sensor cluster "{cluster_id}".

You have been given a batch of sensor readings from your cluster.
Your job is to determine whether the readings indicate a real anomaly
(fire, sensor fault, sudden weather change) or normal conditions.

Use the available tools to inspect the data:
  - get_recent_readings: see the raw sensor events
  - get_sensor_summary: get aggregate stats per sensor type
  - check_threshold: test specific readings against thresholds
  - get_cluster_status: see cluster metadata

After your analysis, respond with a JSON object (and nothing else):
{{
  "anomaly_detected": true/false,
  "anomaly_type": "threshold_breach" | "sensor_fault" | "correlated_event" | "none",
  "affected_sensors": ["sensor-id-1", ...],
  "confidence": 0.0 to 1.0,
  "summary": "Brief explanation of what you found"
}}
"""


# ── Node functions ────────────────────────────────────────────────────────────
# Each node receives the full state and returns a PARTIAL state update.
# LangGraph merges the partial update into the current state using reducers.
# Nodes should only return the fields they actually changed.

def ingest_events(state: ClusterAgentState) -> dict:
    """
    First node — acknowledges the trigger event and sets status to processing.

    In a real implementation this node might also:
      - Validate the incoming event schema
      - Load recent history from the LangGraph Store
      - Decide whether the event is worth classifying (pre-filter)

    For now it just logs and moves on.
    """
    trigger = state.get("trigger_event")
    logger.info(
        "ClusterAgent[%s] ingesting event from source=%s",
        state.get("cluster_id"),
        trigger.source_id if trigger else "unknown",
    )

    # Return only the fields we're changing.
    # LangGraph merges this with the existing state.
    return {
        "status": "processing",
        "error_message": None,   # Clear any previous error
    }


def classify(state: ClusterAgentState) -> dict:
    """
    Stub classify node — used when no LLM is provided.

    Produces a placeholder finding so the rest of the pipeline
    has something to work with end-to-end.
    """
    cluster_id = state.get("cluster_id", "unknown")
    trigger = state.get("trigger_event")

    logger.info(
        "ClusterAgent[%s] classify — STUB (no LLM)",
        cluster_id,
    )

    stub_finding: AnomalyFinding = {
        "finding_id": str(uuid4()),
        "cluster_id": cluster_id,
        "anomaly_type": "stub_placeholder",
        "affected_sensors": [trigger.source_id] if trigger else [],
        "confidence": 0.5,
        "summary": f"[STUB] classify node not yet implemented for cluster {cluster_id}",
        "raw_context": {
            "trigger_event_id": trigger.event_id if trigger else None,
            "event_count_in_window": len(state.get("sensor_events", [])),
        },
    }

    return {
        "anomalies": [stub_finding],
        "status": "complete",
    }


def _make_classify_llm_node(llm_with_tools: BaseChatModel):
    """
    Factory that returns a classify node backed by an LLM with bound tools.

    The returned function:
      1. Sets the tool state so tools can access sensor events.
      2. Builds a system prompt + user message from the state.
      3. Invokes the LLM (which may produce tool_calls or a final answer).
      4. Returns the AIMessage so LangGraph can route to ToolNode or report.
    """

    def classify_llm(state: ClusterAgentState) -> dict:
        cluster_id = state.get("cluster_id", "unknown")
        events = state.get("sensor_events", [])
        trigger = state.get("trigger_event")
        messages = state.get("messages", [])

        # Load tool state so tools can read the sensor events.
        set_tool_state(events, cluster_id)

        logger.info(
            "ClusterAgent[%s] classify — LLM mode (%d events, %d messages)",
            cluster_id,
            len(events),
            len(messages),
        )

        # Build initial messages if this is the first classify call.
        if not messages:
            sys_msg = SystemMessage(
                content=CLASSIFY_SYSTEM_PROMPT.format(cluster_id=cluster_id)
            )
            # Summarize the sensor data for the LLM.
            event_summaries = []
            for e in events[-20:]:
                event_summaries.append(
                    f"  [{e.source_type}] {e.source_id} tick={e.sim_tick} "
                    f"conf={e.confidence:.2f} payload={e.payload}"
                )
            user_content = (
                f"Cluster: {cluster_id}\n"
                f"Events in window: {len(events)}\n"
                f"Trigger event: {trigger.source_id if trigger else 'none'}\n"
                f"Recent readings:\n" + "\n".join(event_summaries)
            )
            user_msg = HumanMessage(content=user_content)
            messages = [sys_msg, user_msg]

        response = llm_with_tools.invoke(messages)

        return {
            "messages": [response],
            "status": "processing",
        }

    return classify_llm


def _parse_llm_findings(state: ClusterAgentState) -> dict:
    """
    Parse the LLM's final text response into an AnomalyFinding.

    This node runs after classify_llm when the LLM is done (no more tool calls).
    It extracts the JSON from the last AI message and converts it to a finding.
    """
    cluster_id = state.get("cluster_id", "unknown")
    messages = state.get("messages", [])
    trigger = state.get("trigger_event")

    # Clean up tool state.
    clear_tool_state()

    # Find the last AI message.
    last_ai = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            last_ai = msg
            break

    if last_ai is None:
        logger.warning("ClusterAgent[%s] no AI message found", cluster_id)
        return {"status": "complete", "anomalies": []}

    # Try to parse JSON from the LLM response.
    try:
        content = last_ai.content.strip()
        # Handle markdown code fences.
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])
        parsed = json.loads(content)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning(
            "ClusterAgent[%s] failed to parse LLM response: %s",
            cluster_id, exc,
        )
        # Fall back to a finding based on the raw text.
        parsed = {
            "anomaly_detected": True,
            "anomaly_type": "llm_parse_fallback",
            "affected_sensors": [trigger.source_id] if trigger else [],
            "confidence": 0.3,
            "summary": last_ai.content[:200],
        }

    findings: list[AnomalyFinding] = []
    if parsed.get("anomaly_detected", False):
        findings.append({
            "finding_id": str(uuid4()),
            "cluster_id": cluster_id,
            "anomaly_type": parsed.get("anomaly_type", "unknown"),
            "affected_sensors": parsed.get("affected_sensors", []),
            "confidence": float(parsed.get("confidence", 0.5)),
            "summary": parsed.get("summary", "LLM detected anomaly"),
            "raw_context": {
                "trigger_event_id": trigger.event_id if trigger else None,
                "event_count_in_window": len(state.get("sensor_events", [])),
                "llm_response": last_ai.content[:500],
            },
        })

    return {
        "anomalies": findings,
        "status": "complete",
    }


def report_findings(state: ClusterAgentState, store: Optional[BaseStore] = None) -> dict:
    """
    Final node — packages anomalies for the supervisor and writes them to
    the cross-agent Store so the supervisor can recall past incidents.

    Store write (when store is provided):
      namespace : ("incidents", cluster_id)
      key       : finding_id  (UUID — stable across restarts with pgvector)
      value     : the full AnomalyFinding dict

    The supervisor reads from ("incidents", cluster_id) in assess_situation
    to build context before making a decision.  This is the primary mechanism
    for cross-agent memory — cluster agents write, supervisor reads.

    Deduplication is handled by key: writing the same finding_id twice is a
    no-op (last write wins, same value).
    """
    anomalies = state.get("anomalies", [])
    cluster_id = state.get("cluster_id", "unknown")

    logger.info(
        "ClusterAgent[%s] reporting %d finding(s) to supervisor",
        cluster_id,
        len(anomalies),
    )

    if store is not None and anomalies:
        for finding in anomalies:
            store.put(
                ("incidents", cluster_id),
                finding["finding_id"],
                finding,
            )
        logger.info(
            "ClusterAgent[%s] wrote %d finding(s) to store namespace ('incidents', '%s')",
            cluster_id,
            len(anomalies),
            cluster_id,
        )

    # No state change needed — anomalies are already in state
    return {}


# ── Routers ──────────────────────────────────────────────────────────────────

def route_after_classify(
    state: ClusterAgentState,
) -> Literal["report_findings", "__end__"]:
    """
    Router for stub mode — classify always goes to report_findings.
    """
    if state.get("status") == "error":
        logger.warning(
            "ClusterAgent[%s] exiting due to error: %s",
            state.get("cluster_id"),
            state.get("error_message"),
        )
        return "__end__"

    return "report_findings"


def route_after_classify_llm(
    state: ClusterAgentState,
) -> Literal["tool_node", "parse_findings", "__end__"]:
    """
    Router for LLM mode — checks if the LLM wants to call tools.

    If the last AI message has tool_calls → route to tool_node.
    Otherwise → route to parse_findings to extract the answer.
    On error → exit.
    """
    if state.get("status") == "error":
        return "__end__"

    messages = state.get("messages", [])
    if messages:
        last = messages[-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "tool_node"

    return "parse_findings"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_cluster_agent_graph(
    llm: Optional[BaseChatModel] = None,
    store: Optional[BaseStore] = None,
):
    """
    Compile and return the cluster agent subgraph.

    Parameters
    ──────────
    llm   : Optional LangChain chat model.  When provided, the classify
            node uses LLM + ToolNode in a ReAct loop.  When None (default),
            a deterministic stub classify is used instead.
    store : Optional LangGraph Store.  When provided, report_findings writes
            each AnomalyFinding to ("incidents", cluster_id) so the supervisor
            can recall past incidents across runs.
            Pass InMemoryStore for dev, AsyncPostgresStore for production.

    Returns a compiled LangGraph graph ready for .invoke() or .stream().

    To test the cluster agent in isolation:
      graph = build_cluster_agent_graph()
      result = graph.invoke({
          "cluster_id": "cluster-north",
          "workflow_id": "test-run-1",
          "sensor_events": [],
          "trigger_event": some_sensor_event,
          "messages": [],
          "anomalies": [],
          "status": "idle",
          "error_message": None,
      })
    """
    builder = StateGraph(ClusterAgentState)

    builder.add_node("ingest_events", ingest_events)
    builder.add_node("report_findings", report_findings)

    builder.add_edge(START, "ingest_events")

    if llm is not None:
        # ── LLM mode: classify_llm → tool_node loop → parse_findings ──
        llm_with_tools = llm.bind_tools(SENSOR_TOOLS)
        classify_llm_node = _make_classify_llm_node(llm_with_tools)

        builder.add_node("classify", classify_llm_node)
        builder.add_node("tool_node", ToolNode(SENSOR_TOOLS))
        builder.add_node("parse_findings", _parse_llm_findings)

        builder.add_edge("ingest_events", "classify")
        builder.add_conditional_edges("classify", route_after_classify_llm)
        builder.add_edge("tool_node", "classify")
        builder.add_edge("parse_findings", "report_findings")

        logger.info("ClusterAgent subgraph compiled (LLM mode)")
    else:
        # ── Stub mode: deterministic classify ──────────────────────────
        builder.add_node("classify", classify)
        builder.add_edge("ingest_events", "classify")
        builder.add_conditional_edges("classify", route_after_classify)

        logger.info("ClusterAgent subgraph compiled (stub mode)")

    builder.add_edge("report_findings", END)

    # Passing store=store makes LangGraph inject it into any node whose
    # signature includes `store: Optional[BaseStore]`.
    # store=None is safe — nodes receive None and guard against it.
    compiled = builder.compile(store=store)
    return compiled


# Module-level compiled graph (stub mode).
# Import this in the supervisor and in tests:
#   from ogar.agents.cluster.graph import cluster_agent_graph
# The graph is compiled once when the module is first imported.
cluster_agent_graph = build_cluster_agent_graph()
