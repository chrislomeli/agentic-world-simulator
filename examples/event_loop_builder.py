#!/usr/bin/env python3
"""
event_loop_builder.py — Factory functions for the event loop + supervisor callback.

Three functions, three concerns:

  make_supervisor_callback(graph, results)
      Returns an on_batch callback that invokes the supervisor graph.
      The callback is a closure — it captures the graph and results
      accumulator, so the EventLoop never needs to know about agents.

  build_event_loop(location_store, on_batch, ...)
      Returns a configured EventLoop.  Accepts *any* on_batch callback,
      so it can be used with or without a supervisor graph.

  run_pipeline_with_event_loop(pipeline, event_loop, ...)
      Runs the pipeline and event loop concurrently.  Cancels the event
      loop when the pipeline finishes, then runs one final drain pass.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from bridge.pipeline_runner import PipelineRunner
from event_loop.loop import EventLoop, EventLoopConfig
from event_loop.sensor_filter import ScoringFilter
from event_loop.store import LocationStateStore


# ── Callback factory ─────────────────────────────────────────────────────────

def make_supervisor_callback(
    supervisor_graph: CompiledStateGraph,
    results: list[tuple[int, dict]],
) -> Callable[[dict[str, Any]], None]:
    """
    Return an on_batch callback that invokes the supervisor graph.

    Parameters
    ──────────
    supervisor_graph : Compiled LangGraph supervisor graph.
    results          : Accumulator list — each invocation appends
                       (cycle, result_dict).  The caller owns this list
                       and can inspect it after the run.

    The returned callback reads batch["cycle"] (stamped by EventLoop)
    so it never needs a reference to the pipeline.
    """

    def on_batch(batch: dict[str, Any]) -> None:
        cycle = batch["cycle"]
        print(f"\n--- Event loop trigger at cycle {cycle} ---")
        for cid, events in batch["events_by_cluster"].items():
            print(f"  {cid}: {len(events)} recent state(s)")

        result = supervisor_graph.invoke(
            {
                "active_cluster_ids": batch["active_cluster_ids"],
                "events_by_cluster": batch["events_by_cluster"],
                "cluster_findings": [],
                "messages": [],
                "pending_commands": [],
                "situation_summary": None,
                "status": "idle",
                "error_message": None,
            },
            config={"run_name": f"supervisor-cycle-{cycle}"},
        )
        results.append((cycle, result))

    return on_batch


# ── Event loop factory ───────────────────────────────────────────────────────

def build_event_loop(
    store: LocationStateStore,
    on_batch: Callable[[dict[str, Any]], None],
    *,
    cycle_speed_seconds: float = 0.1,
    max_cycles: int | None = None,
) -> EventLoop:
    """
    Build a PIPELINE-mode EventLoop.

    Parameters
    ──────────
    store               : The LocationStateStore the pipeline consumer writes into.
    on_batch            : Callback invoked when one or more locations trigger.
    cycle_speed_seconds : Seconds between filter cycles.
    max_cycles          : Cycle limit.  None = run until cancelled.
    """
    return EventLoop(
        EventLoopConfig(
            mode="PIPELINE",
            cycle_speed_seconds=cycle_speed_seconds,
            max_cycles=max_cycles,
        ),
        store=store,
        sensor_filter=ScoringFilter(),
        on_batch=on_batch,
    )


# ── Orchestrator ────────────────────────────────────────────────────────────

async def run_pipeline_with_event_loop(
    pipeline: PipelineRunner,
    event_loop: EventLoop,
    *,
    num_ticks: int = 20,
    tick_interval: float = 0.0,
) -> None:
    """
    Run the pipeline and event loop concurrently, then drain.

    Lifecycle
    ─────────
    1. Start the pipeline (produces data into the shared store).
    2. Start the event loop (reads from the store, calls on_batch).
    3. When the pipeline finishes, cancel the event loop.
    4. Run one final event-loop pass to catch anything the loop missed.

    Parameters
    ──────────
    pipeline      : A started-or-startable PipelineRunner.
    event_loop    : An EventLoop (PIPELINE mode) wired to the same store.
    num_ticks     : How many world ticks to run.
    tick_interval : Seconds between ticks (0.0 = as fast as possible).
    """

    async def _run_pipeline() -> None:
        await pipeline.start(num_ticks=num_ticks, tick_interval=tick_interval)
        while pipeline.is_running:
            await asyncio.sleep(0.05)
        await pipeline.stop()

    async def _run_event_loop() -> None:
        await asyncio.sleep(0.05)  # let the pipeline start producing
        try:
            await event_loop.run()
        except asyncio.CancelledError:
            pass

    # Run both — cancel the event loop when the pipeline finishes.
    loop_task = asyncio.create_task(_run_event_loop())
    await _run_pipeline()
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass

    # Final drain — one pass to catch any data the loop missed.
    final = build_event_loop(
        event_loop.store,
        event_loop.on_batch,
        cycle_speed_seconds=0.0,
        max_cycles=1,
    )
    await final.run()
