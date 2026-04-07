"""
ogar.actuators

Actuator abstraction — the "do something" side of the agent loop.

Sensors detect.  Agents decide.  Actuators act.

  - ActuatorBase (base.py)      — ABC with execute() and handle().
  - ActuatorCommand / Result    — envelope models for commands and results.

Concrete actuators (e.g., DispatchFireCrew, EvacuateZone) will
be added as the agent graphs mature.  Each actuator handles one
command_type and returns an ActuatorResult.
"""

from actuators.base import ActuatorBase as ActuatorBase
from actuators.base import ActuatorCommand as ActuatorCommand
from actuators.base import ActuatorResult as ActuatorResult

__all__ = [
    "ActuatorBase",
    "ActuatorCommand",
    "ActuatorResult",
]
