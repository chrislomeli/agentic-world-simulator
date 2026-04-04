"""
ogar — Orchestrator-Grade Agent Runtime

Top-level package. Nothing lives here yet except the version string.
Sub-packages are imported explicitly where needed — no star imports.

Package layout (grows as we build):

  ogar/
    transport/    ← Kafka topic names + the SensorEvent envelope schema
    sensors/      ← Abstract sensor base class + mock implementations
    actuators/    ← Abstract actuator base class + mock implementations  (coming)
    agents/       ← LangGraph subgraphs: cluster agent, supervisor        (coming)
    tools/        ← ToolSpec / ToolRegistry for LangGraph ToolNode        (coming)
    workflow/     ← WorkflowRunner interface + asyncio stub               (coming)
    hitl/         ← HumanApprovalGate interface + asyncio stub            (coming)
    memory/       ← LangGraph Store + Postgres checkpointer               (coming)
    infrastructure/ ← InstrumentedGraph, NodeMiddleware, LLM client       (coming)
"""

__version__ = "0.1.0"
