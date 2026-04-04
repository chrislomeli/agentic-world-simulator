"""
ogar.workflow.runner

WorkflowRunner interface — the abstraction layer over Temporal.

Why this abstraction exists
────────────────────────────
The rest of the system (bridge consumer, agents) should not know
whether workflows are running via:
  - asyncio tasks (our stub, for development and demos)
  - Temporal (production-grade durable execution)
  - anything else

By programming to this interface, swapping the runtime is mechanical:
change one line where the WorkflowRunner is constructed.

What a WorkflowRunner does
──────────────────────────
start()   → Begin executing a workflow function, identified by a
            unique workflow_id.  If a workflow with that ID is already
            running, this is a no-op (deduplication).

signal()  → Send a named signal with a payload to a running workflow.
            Used for:
              - Delivering new sensor events to a long-running cluster agent
              - Delivering human approval decisions to a waiting workflow

get_status() → Check whether a workflow is running, completed, or unknown.

Temporal mapping
────────────────
When Temporal is added, these methods map to:
  start()      → temporal_client.start_workflow()
                 with WorkflowIdReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY
  signal()     → temporal_client.get_workflow_handle(id).signal()
  get_status() → temporal_client.get_workflow_handle(id).describe()

The deduplication guarantee is the same in both implementations:
calling start() twice with the same workflow_id is safe.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Coroutine


class WorkflowStatus(str, Enum):
    """
    The possible states of a workflow execution.

    RUNNING   — workflow is currently executing or waiting for a signal
    COMPLETED — workflow finished successfully
    FAILED    — workflow terminated with an error
    UNKNOWN   — no workflow with this ID exists (never started, or expired)
    """
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    UNKNOWN   = "UNKNOWN"


class WorkflowRunner(ABC):
    """
    Abstract interface for durable workflow execution.

    Both the asyncio stub and the Temporal implementation must satisfy
    this interface.  The bridge consumer and any code that starts
    workflows depends only on this class, never on a concrete implementation.
    """

    @abstractmethod
    async def start(
        self,
        workflow_id: str,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Start executing a workflow function.

        Parameters
        ──────────
        workflow_id : Unique identifier for this workflow execution.
                      If a workflow with this ID is already RUNNING,
                      this call is a no-op (idempotent start).

                      Convention for sensor-driven workflows:
                        "{cluster_id}::{source_type}"
                      This means one long-running workflow per sensor
                      type per cluster — new events are delivered via
                      signal(), not by starting new workflows.

        fn          : The async function (coroutine) to execute.
                      In the Temporal version this becomes a registered
                      Workflow function.

        *args       : Positional arguments passed to fn.
        **kwargs    : Keyword arguments passed to fn.
        """
        ...

    @abstractmethod
    async def signal(
        self,
        workflow_id: str,
        signal_name: str,
        payload: Any = None,
    ) -> None:
        """
        Deliver a named signal to a running workflow.

        Parameters
        ──────────
        workflow_id  : The ID of the workflow to signal.
                       Must be currently RUNNING.
        signal_name  : Name of the signal.  The workflow must be
                       waiting on a signal with this name.
                       Convention: lowercase, underscore-separated.
                       e.g. "new_sensor_event", "human_approved"
        payload      : Any serialisable value to pass with the signal.
                       The workflow receives this as an argument.
        """
        ...

    @abstractmethod
    async def get_status(self, workflow_id: str) -> WorkflowStatus:
        """
        Return the current status of a workflow.

        Returns WorkflowStatus.UNKNOWN if no workflow with this ID
        has ever been started (or if it has been garbage-collected).
        """
        ...
