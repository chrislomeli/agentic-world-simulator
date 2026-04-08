"""
ogar.bridge.consumer

Async event bridge consumer — reads SensorEvents from a queue
and groups them by cluster for the supervisor to process.

Responsibility
──────────────
The consumer sits between the transport queue and the supervisor.
It collects sensor events as they arrive and groups them by cluster_id.
The supervisor then fans out to cluster agents with these grouped events.

This is Option B architecture: the supervisor owns agent orchestration.
The consumer's only job is to drain the queue and group events — it does
NOT invoke cluster agents directly.

Why async?
──────────
The publisher (world engine ticking + sensor emission) is async.
Running the consumer as an async loop lets it drain the queue while
the publisher is still producing events.

Usage
─────
  # Concurrent: publisher and consumer run as parallel async tasks.
  # The orchestrator periodically pulls batched events for the supervisor.

  consumer = EventBridgeConsumer(queue=queue)
  pub_task = asyncio.create_task(publisher.run(ticks=20))
  con_task = asyncio.create_task(consumer.run())

  # Periodically (or after publisher finishes):
  batch = consumer.drain_batch()   # pull + reset
  result = supervisor_graph.invoke({
      "active_cluster_ids": list(batch.keys()),
      "events_by_cluster": batch,
      ...
  })

  # When done:
  consumer.stop()
  await con_task
"""

from __future__ import annotations

import asyncio
import logging

from transport.queue import SensorEventQueue
from transport.schemas import SensorEvent

logger = logging.getLogger(__name__)


class EventBridgeConsumer:
    """
    Async consumer that collects SensorEvents grouped by cluster.

    Drains the queue and accumulates events into events_by_cluster.
    The supervisor reads events_by_cluster to populate cluster agents
    via the Send API fan-out.

    Parameters
    ──────────
    queue : The SensorEventQueue to consume from.
    """

    def __init__(self, *, queue: SensorEventQueue) -> None:
        self._queue = queue
        self.events_by_cluster: dict[str, list[SensorEvent]] = {}
        self.events_consumed: int = 0
        self._stop_requested: bool = False

    def stop(self) -> None:
        """Signal the consumer to stop after the current event."""
        logger.info("EventBridgeConsumer stop requested")
        self._stop_requested = True

    async def run(self, max_events: int | None = None) -> None:
        """
        Run the consumer loop.

        Parameters
        ──────────
        max_events : If provided, stop after consuming this many events.
                     If None, run until stop() is called or the task is cancelled.
        """
        self._stop_requested = False
        self.events_consumed = 0
        self.events_by_cluster = {}

        logger.info(
            "EventBridgeConsumer starting — limit=%s",
            max_events if max_events is not None else "∞",
        )

        while True:
            if self._stop_requested:
                logger.info(
                    "EventBridgeConsumer stopped after %d events",
                    self.events_consumed,
                )
                break

            if max_events is not None and self.events_consumed >= max_events:
                logger.info(
                    "EventBridgeConsumer reached event limit (%d)",
                    max_events,
                )
                break

            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                continue

            self.events_consumed += 1
            cluster_id = event.cluster_id

            logger.debug(
                "Consumed event %s from %s (cluster=%s, tick=%d)",
                event.event_id,
                event.source_id,
                cluster_id,
                event.sim_tick,
            )

            if cluster_id not in self.events_by_cluster:
                self.events_by_cluster[cluster_id] = []
            self.events_by_cluster[cluster_id].append(event)

            self._queue.task_done()

    def drain_batch(self) -> dict[str, list[SensorEvent]]:
        """
        Pull the current batch of grouped events and reset the buffer.

        This is the interface between the async consumer and the sync
        supervisor.  The orchestrator calls this periodically to get
        accumulated events, then passes them to supervisor_graph.invoke().

        Returns
        ───────
        dict mapping cluster_id → list of SensorEvents accumulated since
        the last drain.  The internal buffer is cleared after this call.

        Thread-safety: called from the same asyncio loop as run(), so
        no lock is needed.  If you move to threads, add a Lock.
        """
        batch = self.events_by_cluster
        self.events_by_cluster = {}
        drained = self.events_consumed
        self.events_consumed = 0
        logger.info(
            "EventBridgeConsumer drained %d events across %d cluster(s)",
            drained, len(batch),
        )
        return batch
