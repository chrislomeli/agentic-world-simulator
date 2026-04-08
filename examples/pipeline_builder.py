#!/usr/bin/env python3
"""
pipeline_builder.py  —  STEP 04: Build and run the pub/sub pipeline

This module is self-contained: it creates the pipeline and can run it
standalone (no supervisor, no agents).

What it builds:
  - SensorEventQueue   (in-memory transport, same shape as a Kafka topic)
  - SensorPublisher    (ticks the world engine, emits sensor events)
  - EventBridgeConsumer (groups events by cluster_id)

All wrapped in a PipelineRunner, which exposes:
  - start() / stop()     — async lifecycle
  - drain_batch()        — pull grouped events (the interface a supervisor uses)
  - run_to_completion()  — convenience: run all ticks, return everything

In production, drain_batch() would read from Kafka instead of an
in-memory queue — but the signature is identical.
"""

from __future__ import annotations

from bridge.pipeline_runner import PipelineRunner
from domains.wildfire.sampler import sample_local_conditions
from event_loop.store import LocationStateStore
from transport.schemas import SensorEvent
from world.generic_engine import GenericWorldEngine
from world.sensor_inventory import SensorInventory

# ─── Factory ──────────────────────────────────────────────────────────────────

def build_pipeline(
    engine: GenericWorldEngine,
    sensor_inventory: SensorInventory,
    *,
    store: LocationStateStore | None = None,
    queue_maxsize: int = 500,
) -> PipelineRunner:
    """
    Create a PipelineRunner wired to the wildfire sampler.

    Parameters
    ──────────
    engine            : The world engine (provides grid state + tick).
    sensor_inventory  : Sensors to poll each tick.
    store             : LocationStateStore the consumer writes into.
                        If None, PipelineRunner creates an internal one.
    queue_maxsize     : Max events buffered before back-pressure.

    Returns
    ───────
    PipelineRunner — call start() to begin.  The consumer writes
    aggregated location state into the store.
    """
    return PipelineRunner(
        engine,
        sensor_inventory,
        sampler=sample_local_conditions,
        store=store,
        queue_maxsize=queue_maxsize,
    )


# ─── Standalone runner (Step 04 demo — no supervisor needed) ──────────────────

async def run_pipeline(
    pipeline: PipelineRunner,
    *,
    num_ticks: int = 20,
) -> dict[str, list[SensorEvent]]:
    """
    Run the pipeline to completion and print what was collected.

    This is the Step 04 deliverable: a working pub/sub pipeline that
    publishes sensor events, consumes them, and groups them by cluster.
    No supervisor, no agents — just the data pipeline.

    Returns
    ───────
    dict mapping cluster_id → list of SensorEvents.
    """
    print("=" * 65)
    print(f"Pipeline: running {num_ticks} world ticks")
    print("=" * 65)

    events_by_cluster = await pipeline.run_to_completion(
        num_ticks=num_ticks, tick_interval=0.0,
    )

    # Print summary of what was collected
    total = sum(len(evts) for evts in events_by_cluster.values())
    print(f"\nPipeline complete — {total} events across {len(events_by_cluster)} cluster(s):")
    for cluster_id, events in sorted(events_by_cluster.items()):
        print(f"  {cluster_id}: {len(events)} events")
        # Show a sample event from each cluster
        if events:
            sample = events[0]
            print(f"    sample: tick={sample.sim_tick}  source={sample.source_id}  "
                  f"type={sample.source_type}  payload={sample.payload}")

    return events_by_cluster
