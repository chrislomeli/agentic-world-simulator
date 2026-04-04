"""
ogar.domains.wildfire.cell_state

FireCellState — per-cell state for wildfire simulation.

This defines what data lives on each grid cell in a wildfire scenario:
  - terrain_type : what kind of land (forest, grassland, rock, etc.)
  - vegetation   : density of burnable material (0.0–1.0)
  - fuel_moisture: how wet the fuel is (0.0–1.0)
  - slope        : gradient in degrees
  - fire_state   : UNBURNED, BURNING, or BURNED
  - fire_intensity: how hot the fire is (0.0–1.0)
  - fire_start_tick: when the fire started in this cell

TerrainType and FireState enums are imported from ogar.world.grid
(their original home) and re-exported here so that domain code can
import everything from one place.
"""

from __future__ import annotations

from typing import Optional

from ogar.world.cell_state import CellState
from ogar.world.grid import FireState, TerrainType


# ── Cell state ───────────────────────────────────────────────────────────────

class FireCellState(CellState):
    """
    Per-cell state for wildfire simulation.

    This is a Pydantic model that implements the CellState ABC.
    The generic grid carries these without interpreting them —
    the FirePhysicsModule reads and produces new FireCellState
    instances via StateEvents.
    """

    # Terrain properties (set once during scenario setup, don't change)
    terrain_type: TerrainType = TerrainType.GRASSLAND
    vegetation: float = 0.5
    fuel_moisture: float = 0.3
    slope: float = 0.0

    # Fire state (changes during simulation via StateEvents)
    fire_state: FireState = FireState.UNBURNED
    fire_intensity: float = 0.0
    fire_start_tick: Optional[int] = None

    def summary_label(self) -> str:
        """Used by the engine for logging and grid summary counts."""
        return self.fire_state.value

    @property
    def is_burnable(self) -> bool:
        """
        Can fire spread to this cell?

        Rock, water, and already-burned cells cannot catch fire.
        Cells with zero vegetation also cannot burn.
        """
        if self.terrain_type in (TerrainType.ROCK, TerrainType.WATER):
            return False
        if self.fire_state != FireState.UNBURNED:
            return False
        if self.vegetation <= 0.0:
            return False
        return True

    def ignited(self, tick: int, intensity: float = 0.5) -> "FireCellState":
        """
        Return a new state with the cell on fire.

        Does NOT mutate self — returns a new instance for use in
        StateEvent. This is the immutable pattern the generic engine
        expects.
        """
        return self.model_copy(update={
            "fire_state": FireState.BURNING,
            "fire_intensity": max(0.0, min(1.0, intensity)),
            "fire_start_tick": tick,
        })

    def extinguished(self) -> "FireCellState":
        """Return a new state with the fire burned out."""
        return self.model_copy(update={
            "fire_state": FireState.BURNED,
            "fire_intensity": 0.0,
        })
