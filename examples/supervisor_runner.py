#!/usr/bin/env python3
"""
supervisor_runner.py  —  STEP 05: Wire the supervisor to the pipeline

The orchestrator connects the pipeline to the supervisor graph:

    Pipeline (LangGraph-free)
        → drain_batch() → events grouped by cluster
    Supervisor graph (single invocation does everything)
        → fan_out_to_clusters (Send API) → cluster agents in parallel
        → [synchronization barrier]
        → assess_situation → decide_actions → dispatch_commands

The orchestrator's job is simple: periodically drain events and invoke
the supervisor.  All agent logic lives inside the graph.

Usage
─────
  pipeline = build_pipeline(engine, sensor_inventory)
  supervisor_graph = build_supervisor_graph(llm=llm, store=store)

  results = await run_with_supervisor(
      pipeline=pipeline,
      supervisor_graph=supervisor_graph,
      num_ticks=20,
      supervisor_interval=10,
  )
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import langsmith

from bridge.pipeline_runner import PipelineRunner
from transport.schemas import SensorEvent

logger = logging.getLogger(__name__)

# Type alias for the event source callable.
# In-memory: pipeline.drain_batch
# Kafka:     kafka_consumer.poll_and_group
EventSourceFn = Callable[[], dict[str, list[SensorEvent]]]


async def run_with_supervisor(
    *,
    pipeline: PipelineRunner,
    supervisor_graph: Any,
    num_ticks: int = 20,
    supervisor_interval: int = 10,
    mode: str = "STUB",
) -> list[tuple[int, dict]]:
    """
    Run the pipeline with periodic supervisor invocations.

    Each interval: drain events → invoke supervisor graph (which
    internally fans out to cluster agents, waits, correlates, decides).

    Parameters
    ──────────
    pipeline            : A started (or startable) PipelineRunner.
    supervisor_graph    : Compiled LangGraph supervisor graph.
    num_ticks           : World ticks to simulate.
    supervisor_interval : Invoke supervisor every N ticks.
    mode                : "LLM" or "STUB" — for logging/tracing metadata.

    Returns
    ───────
    List of (tick, result) tuples from each supervisor invocation.
    """
    print("=" * 65)
    print(f"Supervisor: {num_ticks} ticks, invoking every {supervisor_interval}")
    print("=" * 65)

    supervisor_results: list[tuple[int, dict]] = []
    get_events: EventSourceFn = pipeline.drain_batch

    with langsmith.trace(
        name="ogar-pipeline",
        run_type="chain",
        metadata={
            "num_ticks": num_ticks,
            "mode": mode,
            "supervisor_interval": supervisor_interval,
        },
    ):
        await pipeline.start(num_ticks=num_ticks, tick_interval=0.0)

        last_supervisor_tick = 0
        while pipeline.is_running:
            await asyncio.sleep(0.05)
            ticks_now = pipeline.ticks_completed

            if (ticks_now > 0
                    and ticks_now % supervisor_interval == 0
                    and ticks_now > last_supervisor_tick):

                batch = get_events()
                if batch:
                    supervisor_results.append(
                        _invoke_supervisor(supervisor_graph, batch, ticks_now, mode)
                    )
                    last_supervisor_tick = ticks_now

        # Final drain: pick up any trailing events
        final_batch = get_events()
        if final_batch:
            supervisor_results.append(
                _invoke_supervisor(
                    supervisor_graph, final_batch,
                    pipeline.ticks_completed, mode, label="final",
                )
            )

        await pipeline.stop()

    return supervisor_results


def _invoke_supervisor(
    supervisor_graph: Any,
    batch: dict[str, list],
    tick: int,
    mode: str,
    label: str | None = None,
) -> tuple[int, dict]:
    """
    Invoke the supervisor graph with a batch of events.

    The supervisor handles everything internally:
      fan-out to cluster agents → synchronization → assess → decide → dispatch
    """
    run_label = label or f"tick-{tick}"
    print(f"\n--- Supervisor invocation: {run_label} ---")
    for cid, events in batch.items():
        print(f"  {cid}: {len(events)} events")

    with langsmith.trace(
        name=f"ogar-supervisor-{run_label}",
        run_type="chain",
        metadata={"mode": mode, "tick": tick},
    ):
        result = supervisor_graph.invoke(
            {
                "active_cluster_ids": list(batch.keys()),
                "events_by_cluster": batch,
                "cluster_findings": [],
                "messages": [],
                "pending_commands": [],
                "situation_summary": None,
                "status": "idle",
                "error_message": None,
            },
            config={"run_name": f"supervisor-{run_label}"},
        )

    return tick, result
