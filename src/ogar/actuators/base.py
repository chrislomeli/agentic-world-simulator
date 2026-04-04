"""
ogar.actuators.base

Abstract base class for all actuators.

Actuators are symmetric to sensors — but in the output direction.

  Sensors  : world → SensorEvent envelope → agent
  Actuators: agent → ActuatorCommand envelope → world consequence

The same envelope design applies:
  - ActuatorCommand is domain-agnostic (routing + payload)
  - ActuatorResult is domain-agnostic (outcome + payload)
  - Concrete actuators unpack command.payload and know what to do with it
  - The agent never touches the payload content — it only constructs it

Actuator lifecycle
──────────────────
  1. Supervisor agent builds an ActuatorCommand with structured output.
  2. Command is published to the commands.actuators Kafka topic.
  3. Bridge consumer routes the command to the right actuator by command_type.
  4. Actuator.execute(command) runs.
  5. Actuator returns ActuatorResult (success/failure + output payload).
  6. Result is published to results.actuators Kafka topic.
  7. (Future) Agents can subscribe to results to close the feedback loop.

For now (pre-Kafka) the command routing happens in-process.
The envelope and interface are the same either way.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── Command envelope ──────────────────────────────────────────────────────────

class ActuatorCommand(BaseModel):
    """
    The transport envelope for all actuator commands.

    Symmetric to SensorEvent — the envelope carries routing information
    and an opaque payload.  The actuator unpacks the payload.

    command_id   : UUID. Unique per command. Used for audit and dedup.
    command_type : Opaque string tag. Routes to the right actuator.
                   e.g. "alert", "escalate", "suppress", "drone_task"
    source_agent : Which agent issued this command. For audit trail.
    cluster_id   : Which cluster this command relates to.
    timestamp    : When the command was issued (UTC).
    priority     : 1 (low) to 5 (high). Actuators may queue by priority.
    payload      : Domain-specific command data. Actuator unpacks this.
    metadata     : Optional pass-through extras.
    """
    command_id: str
    command_type: str
    source_agent: str
    cluster_id: str
    timestamp: datetime
    priority: int = 3          # Default medium priority
    payload: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}

    @classmethod
    def create(
        cls,
        *,
        command_type: str,
        source_agent: str,
        cluster_id: str,
        payload: Dict[str, Any],
        priority: int = 3,
        metadata: Dict[str, Any] | None = None,
    ) -> "ActuatorCommand":
        """
        Factory method — auto-generates command_id and timestamp.
        Use this instead of the constructor directly.
        """
        return cls(
            command_id=str(uuid4()),
            command_type=command_type,
            source_agent=source_agent,
            cluster_id=cluster_id,
            timestamp=datetime.now(timezone.utc),
            priority=priority,
            payload=payload,
            metadata=metadata or {},
        )


# ── Result envelope ───────────────────────────────────────────────────────────

class ActuatorResult(BaseModel):
    """
    What an actuator returns after executing a command.

    result_id  : UUID for this result.
    command_id : Links back to the ActuatorCommand that triggered this.
    success    : True if the actuator completed its action.
    timestamp  : When the result was produced (UTC).
    payload    : Domain-specific output. e.g. {"alert_sent_to": ["ops@..."]}
    error      : Error message if success=False.
    """
    result_id: str
    command_id: str
    success: bool
    timestamp: datetime
    payload: Dict[str, Any] = {}
    error: Optional[str] = None

    @classmethod
    def success_result(
        cls,
        command_id: str,
        payload: Dict[str, Any] | None = None,
    ) -> "ActuatorResult":
        """Factory for a successful result."""
        return cls(
            result_id=str(uuid4()),
            command_id=command_id,
            success=True,
            timestamp=datetime.now(timezone.utc),
            payload=payload or {},
        )

    @classmethod
    def failure_result(
        cls,
        command_id: str,
        error: str,
    ) -> "ActuatorResult":
        """Factory for a failed result."""
        return cls(
            result_id=str(uuid4()),
            command_id=command_id,
            success=False,
            timestamp=datetime.now(timezone.utc),
            error=error,
        )


# ── Abstract base class ───────────────────────────────────────────────────────

class ActuatorBase(ABC):
    """
    Abstract base for all actuator implementations.

    Subclasses MUST implement:
      command_type : class attribute — which command_type this handles
      execute(command) → ActuatorResult

    The base class handles:
      - Logging command receipt and result
      - Routing guard (reject commands meant for other actuators)
    """

    @property
    @abstractmethod
    def command_type(self) -> str:
        """
        The command_type string this actuator handles.
        Commands with a different command_type are rejected.

        Define as a class attribute on the subclass:
          class AlertActuator(ActuatorBase):
              command_type = "alert"
        """
        ...

    @abstractmethod
    async def execute(self, command: ActuatorCommand) -> ActuatorResult:
        """
        Execute the command and return a result.

        The subclass unpacks command.payload to get the domain-specific
        instructions.  The base class has already verified that
        command.command_type matches this actuator.

        Should not raise — catch exceptions and return a failure_result.
        """
        ...

    async def handle(self, command: ActuatorCommand) -> ActuatorResult:
        """
        Public entry point — validates command type then calls execute().

        The bridge consumer calls this, not execute() directly.
        This ensures the logging and routing guard always run.
        """
        # ── Routing guard ─────────────────────────────────────────────
        if command.command_type != self.command_type:
            error = (
                f"Actuator {self.__class__.__name__} received command_type="
                f"'{command.command_type}' but handles '{self.command_type}'"
            )
            logger.error(error)
            return ActuatorResult.failure_result(command.command_id, error)

        # ── Execute ───────────────────────────────────────────────────
        logger.info(
            "Actuator %s executing command_id=%s (cluster=%s, priority=%d)",
            self.__class__.__name__,
            command.command_id,
            command.cluster_id,
            command.priority,
        )
        result = await self.execute(command)

        logger.info(
            "Actuator %s result: success=%s command_id=%s",
            self.__class__.__name__,
            result.success,
            command.command_id,
        )
        return result
