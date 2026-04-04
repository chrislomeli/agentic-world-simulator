"""
ogar.workflow.stub

AsyncioWorkflowRunner — the asyncio stub implementation of WorkflowRunner.

What this is
────────────
A simple, in-process implementation of WorkflowRunner that uses
asyncio Tasks instead of Temporal workers.

It provides the same interface as the eventual Temporal implementation
so that all other code (bridge consumer, agents) works unchanged when
Temporal is introduced.

What it gives us now
─────────────────────
  - Deduplication: start() with a duplicate workflow_id is a no-op.
  - Signal delivery: signal() uses asyncio.Queue per workflow so the
    workflow coroutine can await new_event_queue.get() to receive signals.
  - Status tracking: a simple dict maps workflow_id → WorkflowStatus.

What it deliberately does NOT give us
───────────────────────────────────────
  - Crash recovery (tasks die with the process)
  - Persistent execution history
  - The Temporal UI
  - Cross-process signal delivery

All of those come when Temporal replaces this stub.  For development
and demos, this is sufficient.

Signal delivery model
─────────────────────
Each running workflow gets its own asyncio.Queue for incoming signals.
Signals are (signal_name, payload) tuples.

The workflow coroutine reads from its signal queue like this:

    # Inside a workflow function:
    signal_name, payload = await runner.receive_signal(workflow_id)
    if signal_name == "new_sensor_event":
        process(payload)

We expose receive_signal() as a helper — this is the stub-only method
that the workflow function calls.  Temporal workflows use a different
mechanism (workflow.wait_for_signal), so workflow functions will need
a small adapter when Temporal is introduced.

Usage
─────
  runner = AsyncioWorkflowRunner()

  # Start a workflow (idempotent — safe to call multiple times)
  await runner.start("cluster-north::temperature", run_cluster_agent, initial_event)

  # Send a signal (new sensor event arrives)
  await runner.signal("cluster-north::temperature", "new_sensor_event", event)

  # Check status
  status = await runner.get_status("cluster-north::temperature")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple

from ogar.workflow.runner import WorkflowRunner, WorkflowStatus

logger = logging.getLogger(__name__)

# Type alias for a signal tuple stored in the per-workflow queue.
# (signal_name, payload) — the workflow reads these in order.
_Signal = Tuple[str, Any]


class AsyncioWorkflowRunner(WorkflowRunner):
    """
    In-process WorkflowRunner backed by asyncio Tasks and Queues.

    Replace this with a Temporal-backed implementation when ready.
    The interface is identical — the bridge consumer and agents never
    need to change.
    """

    def __init__(self) -> None:
        # Maps workflow_id → current status.
        # Populated by start(), updated when the task finishes or fails.
        self._statuses: Dict[str, WorkflowStatus] = {}

        # Maps workflow_id → asyncio Task.
        # Kept so we can cancel tasks on shutdown.
        self._tasks: Dict[str, asyncio.Task] = {}

        # Maps workflow_id → asyncio.Queue[_Signal].
        # Each workflow reads from its own queue to receive signals.
        self._signal_queues: Dict[str, asyncio.Queue[_Signal]] = {}

    # ── WorkflowRunner interface ──────────────────────────────────────────────

    async def start(
        self,
        workflow_id: str,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Start a workflow as an asyncio Task.

        If a workflow with workflow_id is already RUNNING, this is a no-op.
        This mirrors Temporal's WorkflowIdReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY.

        The workflow function receives (workflow_id, signal_queue, *args, **kwargs)
        so it can call receive_signal() to wait for incoming signals.
        """
        # ── Deduplication check ───────────────────────────────────────
        if self._statuses.get(workflow_id) == WorkflowStatus.RUNNING:
            logger.debug(
                "start() called for workflow_id=%s which is already RUNNING — no-op",
                workflow_id,
            )
            return

        # ── Create signal queue for this workflow ─────────────────────
        # Even if there was a previous (completed/failed) run with this ID,
        # we create a fresh queue for the new run.
        signal_queue: asyncio.Queue[_Signal] = asyncio.Queue()
        self._signal_queues[workflow_id] = signal_queue

        # ── Create and register the task ──────────────────────────────
        async def _run_with_lifecycle() -> None:
            """
            Wrapper that updates status before and after the workflow runs.
            This is how we track RUNNING → COMPLETED/FAILED transitions.
            """
            self._statuses[workflow_id] = WorkflowStatus.RUNNING
            logger.info("Workflow STARTED: %s", workflow_id)
            try:
                # Pass workflow_id and the signal queue as the first two
                # arguments so the workflow can identify itself and receive signals.
                await fn(workflow_id, signal_queue, *args, **kwargs)
                self._statuses[workflow_id] = WorkflowStatus.COMPLETED
                logger.info("Workflow COMPLETED: %s", workflow_id)
            except asyncio.CancelledError:
                # Task was cancelled (e.g. during shutdown) — not a failure.
                self._statuses[workflow_id] = WorkflowStatus.FAILED
                logger.info("Workflow CANCELLED: %s", workflow_id)
                raise
            except Exception as exc:
                self._statuses[workflow_id] = WorkflowStatus.FAILED
                logger.error("Workflow FAILED: %s — %s", workflow_id, exc, exc_info=True)

        task = asyncio.create_task(_run_with_lifecycle(), name=f"workflow:{workflow_id}")
        self._tasks[workflow_id] = task

    async def signal(
        self,
        workflow_id: str,
        signal_name: str,
        payload: Any = None,
    ) -> None:
        """
        Deliver a signal to a running workflow.

        The signal is put onto the workflow's asyncio.Queue.
        The workflow coroutine reads it with receive_signal().

        If the workflow is not running, logs a warning and discards
        the signal.  In Temporal, signalling a non-existent workflow
        raises an error — we'll handle that more strictly when Temporal
        is added.
        """
        queue = self._signal_queues.get(workflow_id)
        if queue is None or self._statuses.get(workflow_id) != WorkflowStatus.RUNNING:
            logger.warning(
                "signal() called for workflow_id=%s but workflow is not RUNNING "
                "(status=%s) — signal discarded",
                workflow_id,
                self._statuses.get(workflow_id, WorkflowStatus.UNKNOWN),
            )
            return

        await queue.put((signal_name, payload))
        logger.debug(
            "Signalled workflow_id=%s with signal=%s",
            workflow_id,
            signal_name,
        )

    async def get_status(self, workflow_id: str) -> WorkflowStatus:
        """Return the current status of a workflow."""
        return self._statuses.get(workflow_id, WorkflowStatus.UNKNOWN)

    # ── Stub-only helper (not on the base interface) ──────────────────────────

    async def receive_signal(
        self,
        workflow_id: str,
        timeout_seconds: Optional[float] = None,
    ) -> Optional[_Signal]:
        """
        Wait for and return the next signal for a workflow.

        Called INSIDE a workflow function to receive incoming signals.

        This is a stub-only method.  When Temporal is introduced,
        workflow functions will use Temporal's native signal mechanism
        (await workflow.wait_for_signal("name")) instead of this.

        Returns None if timeout_seconds elapses with no signal.
        Returns (signal_name, payload) on success.

        Example inside a workflow function:
          result = await runner.receive_signal(workflow_id, timeout_seconds=30)
          if result is None:
              # No signal arrived — decide what to do (idle, check sensors, etc.)
              pass
          else:
              signal_name, payload = result
              if signal_name == "new_sensor_event":
                  await handle_event(payload)
        """
        queue = self._signal_queues.get(workflow_id)
        if queue is None:
            logger.error("receive_signal called for unknown workflow_id=%s", workflow_id)
            return None

        try:
            if timeout_seconds is not None:
                # Wait up to timeout_seconds — returns None if no signal arrives.
                signal = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
            else:
                # Block indefinitely until a signal arrives.
                signal = await queue.get()
            return signal
        except asyncio.TimeoutError:
            return None

    async def shutdown(self) -> None:
        """
        Cancel all running workflow tasks and wait for them to finish.

        Call this during application shutdown to clean up gracefully.
        """
        logger.info("WorkflowRunner shutting down — cancelling %d task(s)", len(self._tasks))
        for wf_id, task in self._tasks.items():
            if not task.done():
                task.cancel()
                logger.debug("Cancelled task for workflow_id=%s", wf_id)

        # Wait for all tasks to acknowledge cancellation.
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        logger.info("WorkflowRunner shutdown complete")
