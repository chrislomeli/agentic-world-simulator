"""
event_loop.loop

The event loop — the orchestration layer between sensor data and the agent pipeline.

Responsibilities
────────────────
1. Ingest sensor readings (SIMULATION: generated locally, KAFKA: from topic)
2. Write each reading to the LocationStateStore (one current state per location)
3. Run each reading through the SensorFilter (deterministic, cheap)
4. Collect all locations that triggered in this cycle into a single batch
5. Call on_batch(batch) with the grouped events — the callback decides what
   to do (invoke cluster agents + supervisor, log, discard, etc.)

What the event loop does NOT do
────────────────────────────────
- It does not know about LangGraph, agents, or graphs
- It does not make risk assessments or decisions
- It does not call LLMs
- It does not know the difference between a cluster agent and a supervisor

The on_batch callback is the seam between infrastructure and agents.
In the tutorial, on_batch invokes cluster agents then the supervisor.
In production, on_batch might publish to a Kafka topic or call an HTTP endpoint.

Batch shape
───────────
The batch passed to on_batch has this shape, which matches the input
that _run_cluster_agents() in supervisor_runner.py expects:

    {
        "active_cluster_ids": ["loc-A", "loc-B"],
        "events_by_cluster": {
            "loc-A": [list of recent state dicts from store],
            "loc-B": [list of recent state dicts from store]
        }
    }

Modes
─────
  SIMULATION — generates fake sensor data via SensorGenerator, runs for
               config.simulation_cycles cycles (or forever if None).

  KAFKA      — stub only.  Shows where a Kafka consumer would plug in.
               The rest of the loop logic is identical in both modes.

Usage
─────
  config = EventLoopConfig(
      location_ids=["loc-A", "loc-B", "loc-C"],
      cycle_speed_seconds=1.0,
      simulation_cycles=20,
      mode="SIMULATION",
  )

  loop = EventLoop(config, on_batch=my_handler)
  await loop.run()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from event_loop.sensor_filter import SensorFilter, ThresholdSensorFilter
from event_loop.sensor_generator import SensorGenerator
from event_loop.store import InMemoryLocationStore, LocationStateStore

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class EventLoopConfig:
    """
    Configuration for the EventLoop.

    Parameters
    ──────────
    location_ids        : Sensor locations to monitor.
    cycle_speed_seconds : Seconds to sleep between cycles.  0.0 = as fast as possible.
    simulation_cycles   : How many cycles to run in SIMULATION mode.
                          None means run until cancelled.
    mode                : "SIMULATION" (fake data) or "KAFKA" (stub).
    history_window      : How many recent events to pass per location in the batch.
    """
    location_ids:        list[str]
    cycle_speed_seconds: float = 1.0
    simulation_cycles:   int | None = 20
    mode:                Literal["SIMULATION", "KAFKA"] = "SIMULATION"
    history_window:      int = 10


# ── Event loop ────────────────────────────────────────────────────────────────

class EventLoop:
    """
    Orchestrates sensor ingestion, filtering, batching, and agent handoff.

    Parameters
    ──────────
    config           : EventLoopConfig controlling runtime behaviour.
    store            : LocationStateStore instance.  Defaults to InMemoryLocationStore.
    sensor_filter    : SensorFilter instance.  Defaults to ThresholdSensorFilter.
    sensor_generator : SensorGenerator for SIMULATION mode.  Auto-created if None.
    on_batch         : Callable invoked when one or more locations trigger.
                       Signature: on_batch(batch: dict) -> None.
                       If None, logs the batch and does nothing (useful for testing).
    """

    def __init__(
        self,
        config: EventLoopConfig,
        *,
        store: LocationStateStore | None = None,
        sensor_filter: SensorFilter | None = None,
        sensor_generator: SensorGenerator | None = None,
        on_batch: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._config   = config
        self._store    = store or InMemoryLocationStore()
        self._filter   = sensor_filter or ThresholdSensorFilter()
        self._on_batch = on_batch or _log_batch
        self._cycles_completed = 0

        if config.mode == "SIMULATION":
            self._generator = sensor_generator or SensorGenerator(
                location_ids=config.location_ids
            )
        else:
            self._generator = None

        logger.info(
            "EventLoop initialized — mode=%s  locations=%s  cycle=%.1fs",
            config.mode,
            config.location_ids,
            config.cycle_speed_seconds,
        )

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def cycles_completed(self) -> int:
        """Number of full cycles completed since run() was called."""
        return self._cycles_completed

    async def run(self) -> None:
        """
        Run the event loop until the cycle limit is reached or the task
        is cancelled.

        In SIMULATION mode: generates readings, applies filter, batches, calls on_batch.
        In KAFKA mode: stub only — shows where the consumer would plug in.
        """
        if self._config.mode == "KAFKA":
            await self._run_kafka()
        else:
            await self._run_simulation()

    # ── Simulation mode ───────────────────────────────────────────────────────

    async def _run_simulation(self) -> None:
        max_cycles = self._config.simulation_cycles
        cycle = 0

        logger.info(
            "EventLoop SIMULATION starting — %s cycle(s)",
            max_cycles if max_cycles is not None else "∞",
        )

        while max_cycles is None or cycle < max_cycles:
            cycle += 1
            logger.info("── Cycle %d ──────────────────────────────────────", cycle)

            triggered: dict[str, str] = {}  # location_id → trigger reason

            # ── Step 1: Generate and store readings ───────────────────
            for location_id in self._config.location_ids:
                reading = self._generator.generate(location_id)
                self._store.set(location_id, reading)
                logger.debug(
                    "  [%s] updated: temp=%.1f°C  hum=%.1f%%  "
                    "wind=%.1f m/s  fuel=%.1f%%",
                    location_id,
                    reading["temperature_c"],
                    reading["humidity_pct"],
                    reading["wind_speed_mps"],
                    reading["fuel_moisture_pct"],
                )

            # ── Step 2: Filter — decide which locations triggered ─────
            for location_id in self._config.location_ids:
                recent = self._store.get_recent_events(
                    location_id, n=self._config.history_window
                )
                did_trigger, reason = self._filter.should_trigger(recent)
                if did_trigger:
                    triggered[location_id] = reason
                    logger.info("  TRIGGERED  [%s]  reason: %s", location_id, reason)
                else:
                    logger.debug("  ok         [%s]  %s", location_id, reason)

            # ── Step 3: Build batch and hand off ─────────────────────
            if triggered:
                batch = self._build_batch(triggered)
                logger.info(
                    "  Batch ready — %d location(s) triggered: %s",
                    len(triggered),
                    list(triggered.keys()),
                )
                self._on_batch(batch)
            else:
                logger.info("  No locations triggered this cycle.")

            self._cycles_completed = cycle

            if self._config.cycle_speed_seconds > 0:
                await asyncio.sleep(self._config.cycle_speed_seconds)

        logger.info(
            "EventLoop SIMULATION complete — %d cycle(s) run.",
            self._cycles_completed,
        )

    # ── Kafka mode (stub) ─────────────────────────────────────────────────────

    async def _run_kafka(self) -> None:
        """
        Kafka consumer stub — shows where the real consumer would plug in.

        In production, replace this body with:

            consumer = AIOKafkaConsumer(
                "sensor-readings",
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id="event-loop",
                value_deserializer=lambda m: json.loads(m.decode()),
            )
            await consumer.start()
            try:
                async for msg in consumer:
                    reading = msg.value
                    location_id = reading["location_id"]
                    self._store.set(location_id, reading)
                    recent = self._store.get_recent_events(location_id)
                    did_trigger, reason = self._filter.should_trigger(recent)
                    if did_trigger:
                        batch = self._build_batch({location_id: reason})
                        self._on_batch(batch)
            finally:
                await consumer.stop()

        Note: in a real Kafka setup you would likely accumulate triggered
        locations within a time window and flush as a single batch, rather
        than calling on_batch per message.  The batching strategy depends
        on your latency requirements.
        """
        logger.warning(
            "EventLoop KAFKA mode is a stub — no Kafka connection configured. "
            "See the docstring for the upgrade path."
        )
        # TODO: implement Kafka consumer (see docstring above)
        raise NotImplementedError(
            "KAFKA mode is not yet implemented.  "
            "Use SIMULATION mode for the tutorial."
        )

    # ── Batch builder ─────────────────────────────────────────────────────────

    def _build_batch(
        self,
        triggered: dict[str, str],
    ) -> dict[str, Any]:
        """
        Build the batch dict that on_batch will receive.

        Shape:
            {
                "active_cluster_ids": ["loc-A", "loc-B"],
                "events_by_cluster": {
                    "loc-A": [list of recent state dicts, oldest first],
                    "loc-B": [list of recent state dicts, oldest first]
                }
            }

        This is the exact shape expected by _run_cluster_agents() in
        supervisor_runner.py.  The event loop does not know about that
        function — the shape is a contract defined by the on_batch caller.
        """
        events_by_cluster: dict[str, list[dict]] = {}
        for location_id in triggered:
            events_by_cluster[location_id] = self._store.get_recent_events(
                location_id, n=self._config.history_window
            )

        return {
            "active_cluster_ids": list(triggered.keys()),
            "events_by_cluster": events_by_cluster,
        }


# ── Default on_batch handler ──────────────────────────────────────────────────

def _log_batch(batch: dict[str, Any]) -> None:
    """
    Default on_batch handler — logs the batch and does nothing.

    Replace by passing your own on_batch to EventLoop:

        loop = EventLoop(config, on_batch=my_agent_handler)

    where my_agent_handler runs cluster agents then the supervisor.
    """
    logger.info(
        "would invoke supervisor graph with batch: active=%s  "
        "events=%s",
        batch["active_cluster_ids"],
        {k: len(v) for k, v in batch["events_by_cluster"].items()},
    )
