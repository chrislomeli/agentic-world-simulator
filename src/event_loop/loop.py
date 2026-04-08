"""
event_loop.loop

The event loop — the decision layer between the location state store
and the agent pipeline.

Responsibilities
────────────────
1. Read location state from the LocationStateStore.
2. Run each location through the SensorFilter (deterministic, cheap).
3. Collect all locations that triggered in this cycle into a single batch.
4. Call on_batch(batch) with the grouped events — the callback decides
   what to do (invoke supervisor graph, log, discard, etc.).

What the event loop does NOT do
────────────────────────────────
- It does not ingest raw sensor data (that's the consumer's job).
- It does not know about LangGraph, agents, or graphs.
- It does not make risk assessments or decisions.
- It does not call LLMs.

The on_batch callback is the seam between infrastructure and agents.

Modes
─────
  PIPELINE   — reads from a store that the pipeline consumer populates.
               This is the production path: world engine → sensors →
               queue → consumer → store → event loop → supervisor.

  SIMULATION — generates fake sensor data via SensorGenerator AND reads
               from the store.  Self-contained, no external pipeline needed.
               Useful for standalone testing and tutorials.

Batch shape
───────────
The batch passed to on_batch:
    {
        "active_cluster_ids": ["cluster-north", "cluster-south"],
        "events_by_cluster": {
            "cluster-north": [list of recent state dicts from store],
            "cluster-south": [list of recent state dicts from store]
        }
    }

Usage
─────
  # Pipeline mode — reads from store populated by the consumer:
  loop = EventLoop(
      config=EventLoopConfig(mode="PIPELINE"),
      store=shared_store,
      on_batch=invoke_supervisor,
  )
  await loop.run()

  # Simulation mode — self-contained:
  loop = EventLoop(
      config=EventLoopConfig(
          mode="SIMULATION",
          location_ids=["loc-A", "loc-B"],
      ),
      on_batch=invoke_supervisor,
  )
  await loop.run()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
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
    mode                : "PIPELINE" (reads from store) or "SIMULATION"
                          (generates data + reads from store).
    location_ids        : Sensor locations to monitor.
                          Required for SIMULATION.  Optional for PIPELINE
                          (defaults to store.get_all_location_ids()).
    cycle_speed_seconds : Seconds between filter/batch cycles.
    max_cycles          : How many cycles to run.  None = run until cancelled.
    history_window      : How many recent events to pass per location.
    """
    mode:                Literal["PIPELINE", "SIMULATION"] = "SIMULATION"
    location_ids:        list[str] | None = None
    cycle_speed_seconds: float = 1.0
    max_cycles:          int | None = 20
    history_window:      int = 10


# ── Event loop ────────────────────────────────────────────────────────────────

class EventLoop:
    """
    Polls the LocationStateStore, filters, batches, and hands off to agents.

    Parameters
    ──────────
    config           : EventLoopConfig controlling runtime behaviour.
    store            : LocationStateStore instance.  In PIPELINE mode this is
                       the same store the consumer writes into.
    sensor_filter    : SensorFilter instance.  Defaults to ThresholdSensorFilter.
    sensor_generator : SensorGenerator for SIMULATION mode.  Auto-created if
                       None and mode is SIMULATION.
    on_batch         : Callable invoked when one or more locations trigger.
                       Signature: on_batch(batch: dict) -> None.
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

        # Generator only used in SIMULATION mode
        if config.mode == "SIMULATION":
            if config.location_ids is None:
                raise ValueError(
                    "SIMULATION mode requires location_ids in EventLoopConfig"
                )
            self._generator = sensor_generator or SensorGenerator(
                location_ids=config.location_ids
            )
        else:
            self._generator = None

        logger.info(
            "EventLoop initialized — mode=%s  locations=%s  cycle=%.1fs",
            config.mode,
            config.location_ids or "(from store)",
            config.cycle_speed_seconds,
        )

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def cycles_completed(self) -> int:
        """Number of full cycles completed since run() was called."""
        return self._cycles_completed

    @property
    def store(self) -> LocationStateStore:
        """The LocationStateStore this event loop reads from."""
        return self._store

    async def run(self) -> None:
        """
        Run the event loop until the cycle limit is reached or cancelled.
        """
        max_cycles = self._config.max_cycles
        cycle = 0

        logger.info(
            "EventLoop %s starting — %s cycle(s)",
            self._config.mode,
            max_cycles if max_cycles is not None else "∞",
        )

        while max_cycles is None or cycle < max_cycles:
            cycle += 1
            logger.info("── Cycle %d ──────────────────────────────────────", cycle)

            # ── Step 1: Generate data (SIMULATION only) ──────────────
            if self._generator is not None:
                for location_id in self._config.location_ids:
                    reading = self._generator.generate(location_id)
                    self._store.set(location_id, reading)
                    logger.debug(
                        "  [%s] generated: temp=%.1f°C  hum=%.1f%%",
                        location_id,
                        reading.get("temperature_c", 0),
                        reading.get("humidity_pct", 0),
                    )

            # ── Step 2: Determine which locations to check ───────────
            location_ids = (
                self._config.location_ids
                or self._store.get_all_location_ids()
            )

            if not location_ids:
                logger.debug("  No locations in store yet — waiting.")
                self._cycles_completed = cycle
                if self._config.cycle_speed_seconds > 0:
                    await asyncio.sleep(self._config.cycle_speed_seconds)
                continue

            # ── Step 3: Filter — decide which locations triggered ────
            triggered: dict[str, str] = {}
            for location_id in location_ids:
                recent = self._store.get_recent_events(
                    location_id, n=self._config.history_window
                )
                if not recent:
                    continue
                did_trigger, reason = self._filter.should_trigger(recent)
                if did_trigger:
                    triggered[location_id] = reason
                    logger.info("  TRIGGERED  [%s]  reason: %s", location_id, reason)
                else:
                    logger.debug("  ok         [%s]  %s", location_id, reason)

            # ── Step 4: Build batch and hand off ─────────────────────
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
            "EventLoop complete — %d cycle(s) run.",
            self._cycles_completed,
        )

    # ── Batch builder ─────────────────────────────────────────────────────────

    def _build_batch(
        self,
        triggered: dict[str, str],
    ) -> dict[str, Any]:
        """
        Build the batch dict that on_batch receives.

        Shape:
            {
                "active_cluster_ids": ["cluster-north", ...],
                "events_by_cluster": {
                    "cluster-north": [recent state dicts, oldest first],
                    ...
                }
            }
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
    """Default on_batch handler — logs the batch and does nothing."""
    logger.info(
        "would invoke supervisor graph with batch: active=%s  "
        "events=%s",
        batch["active_cluster_ids"],
        {k: len(v) for k, v in batch["events_by_cluster"].items()},
    )
