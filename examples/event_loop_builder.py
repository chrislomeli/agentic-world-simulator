#!/usr/bin/env python3
import asyncio

from event_loop import EventLoop, EventLoopConfig, ScoringFilter, InMemoryLocationStore
from langgraph.graph.state import CompiledStateGraph


def on_batch(batch: dict) -> None:
    """Callback: event loop triggers this when locations are flagged."""
    tick = pipeline.ticks_completed
    print(f"\n--- Event loop trigger at tick {tick} ---")
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
        config={"run_name": f"supervisor-tick-{tick}"},
    )
    supervisor_results.append((tick, result))


async def build_event_loop(location_store: InMemoryLocationStore,  supervisor_graph: CompiledStateGraph):
    event_loop = EventLoop(
        EventLoopConfig(
            mode="PIPELINE",
            cycle_speed_seconds=0.1,
            max_cycles=None,  # runs until cancelled
        ),
        store=location_store,
        sensor_filter=ScoringFilter(),
        on_batch=on_batch,
    )

    return event_loop




# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(main())
