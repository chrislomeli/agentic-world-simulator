"""
ogar.domains.wildfire.scenarios

Pre-built wildfire scenarios using the generic engine + fire domain.

Each scenario function returns a fully configured GenericWorldEngine
ready to tick.

basic_wildfire
──────────────
A 10×10 grid with mixed terrain:
  - Forest in the north (high fuel, moderate moisture)
  - Grassland in the south (medium fuel, low moisture)
  - Rock ridge through the middle (firebreak with a gap)
  - Urban area in the south-east (buildings to protect)
  - Lake in the north-west (impassable)

Weather: hot, dry, south-west wind.
Ignition: cell (7, 2) in the south-west grassland.

The gap in the rock ridge at (4,6)-(4,7) is the decision point —
will the fire jump the ridge?  The agent has to monitor both sides.
"""

from __future__ import annotations

from typing import Tuple

from domains.wildfire.cell_state import FireCellState, FireState, TerrainType
from domains.wildfire.environment import FireEnvironmentState
from domains.wildfire.physics import FirePhysicsModule
from resources.base import ResourceBase, ResourceStatus
from resources.inventory import ResourceInventory
from world.generic_engine import GenericWorldEngine
from world.generic_grid import GenericTerrainGrid


def create_basic_wildfire() -> GenericWorldEngine[FireCellState]:
    """
    Create a fully configured wildfire scenario.

    Returns a GenericWorldEngine ready to tick.

    Grid layout (10×10):
      Row 0-1 col 0: WATER (lake)
      Row 0-3: FOREST (high vegetation)
      Row 4: ROCK ridge (gap at cols 6-7 with SCRUB)
      Row 5-9: GRASSLAND (dry)
      Row 7-8, col 8-9: URBAN
      Fire starts at (7, 2) — south-west grassland.
      Wind from SW (225°) → pushes fire north-east.
    """
    physics = FirePhysicsModule(
        base_probability=0.15,
        burn_duration_ticks=5,
    )

    # ── Build grid with custom initial states ─────────────────────
    # We use the default factory first, then overwrite cells.
    grid = GenericTerrainGrid(
        rows=10, cols=10,
        initial_state_factory=physics.initial_cell_state,
    )

    # ── North: lake (north-west corner) ───────────────────────────
    for r in range(2):
        grid.update_cell_state(r, 0, FireCellState(
            terrain_type=TerrainType.WATER,
            vegetation=0.0,
        ))

    # ── North: forest (rows 0–3) ─────────────────────────────────
    for r in range(4):
        for c in range(10):
            current = grid.get_cell(r, c).cell_state
            if current.terrain_type == TerrainType.WATER:
                continue
            grid.update_cell_state(r, c, FireCellState(
                terrain_type=TerrainType.FOREST,
                vegetation=0.85,
                fuel_moisture=0.3,
                slope=5.0,  # slight uphill in the north
            ))

    # ── Middle: rock ridge (row 4) ────────────────────────────────
    for c in range(10):
        if c in (6, 7):
            # Gap in the ridge — scrub, fire might jump through.
            grid.update_cell_state(4, c, FireCellState(
                terrain_type=TerrainType.SCRUB,
                vegetation=0.4,
                fuel_moisture=0.2,
            ))
        else:
            grid.update_cell_state(4, c, FireCellState(
                terrain_type=TerrainType.ROCK,
                vegetation=0.0,
            ))

    # ── South: grassland (rows 5–9) ──────────────────────────────
    for r in range(5, 10):
        for c in range(10):
            grid.update_cell_state(r, c, FireCellState(
                terrain_type=TerrainType.GRASSLAND,
                vegetation=0.6,
                fuel_moisture=0.15,
            ))

    # ── South-east: urban area ────────────────────────────────────
    for r in (7, 8):
        for c in (8, 9):
            grid.update_cell_state(r, c, FireCellState(
                terrain_type=TerrainType.URBAN,
                vegetation=0.1,
                fuel_moisture=0.05,
            ))

    # ── Weather: hot, dry, south-west wind ────────────────────────
    environment = FireEnvironmentState(
        temperature_c=38.0,
        humidity_pct=12.0,
        wind_speed_mps=8.0,
        wind_direction_deg=225.0,
        pressure_hpa=1008.0,
    )

    # ── Build engine ──────────────────────────────────────────────
    engine = GenericWorldEngine(
        grid=grid,
        environment=environment,
        physics=physics,
    )

    # ── Initial ignition ──────────────────────────────────────────
    """
      get_cell(7,2).cell_state retrieves the current FireCellState for that cell. Then .ignited(tick=0, intensity=0.8) doesn't modify it — it returns a new FireCellState with fire_state=BURNING. The original cell is untouched.                                                                                                                                                                                                                                                                                                                                                                                                                     
      inject_state takes that new state object and puts it into the grid at (7,2), replacing the old one.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              
      Why not just cell.ignite() directly? Because FireCellState is a Pydantic model and we chose to make it immutable — state changes return new instances via model_copy(update=...). This is what enables the StateEvent pattern: the physics module produces new state objects and the engine applies them atomically, rather than physics code reaching in and mutating cells directly.                                                                                                                                                                                                                                                                     
      The reason we read the cell first is that ignited() is a method on FireCellState, not a constructor — it carries forward all the existing cell's properties (terrain, vegetation, moisture, slope) and only changes the fire-related fields. If you constructed a fresh FireCellState(fire_state=BURNING) you'd lose all the terrain setup.                                                                                                                                                                                                                                                                                                                
      So the read is load-existing-state, .ignited() is create-modified-copy, inject_state is write-back.    
    """
    ignition_state = grid.get_cell(7, 2).cell_state.ignited(tick=0, intensity=0.8)
    engine.inject_state(7, 2, ignition_state)

    return engine


def create_wildfire_resources(grid_rows: int = 10, grid_cols: int = 10) -> ResourceInventory:
    """
    Create a ResourceInventory with sample preparedness assets for the
    basic wildfire scenario.

    Resource layout (matching the 10×10 basic wildfire grid):

      Firetrucks:
        firetruck-1  : cluster-south, at (9, 0) — south-west station
        firetruck-2  : cluster-south, at (9, 9) — south-east station

      Ambulance:
        ambulance-1  : cluster-south, at (8, 5) — central south

      Hospital:
        hospital-1   : cluster-south, at (7, 9) — near urban area, 50 beds

      Helicopter:
        heli-1       : cluster-north, at (0, 5) — northern airfield

    This mirrors a realistic deployment: fire assets near the ignition
    zone (south), medical assets near the urban area (south-east),
    aerial assets at a remote airfield (north).
    """
    inventory = ResourceInventory(grid_rows=grid_rows, grid_cols=grid_cols)

    # ── Firetrucks ────────────────────────────────────────────────
    inventory.register(ResourceBase(
        resource_id="firetruck-1",
        resource_type="firetruck",
        cluster_id="cluster-south",
        grid_row=9, grid_col=0,
        capacity=500.0,
        available=500.0,
        mobile=True,
        metadata={"unit": "gallons", "crew_size": 4, "model": "Type 1"},
    ))
    inventory.register(ResourceBase(
        resource_id="firetruck-2",
        resource_type="firetruck",
        cluster_id="cluster-south",
        grid_row=9, grid_col=9,
        capacity=500.0,
        available=500.0,
        mobile=True,
        metadata={"unit": "gallons", "crew_size": 4, "model": "Type 3"},
    ))

    # ── Ambulance ─────────────────────────────────────────────────
    inventory.register(ResourceBase(
        resource_id="ambulance-1",
        resource_type="ambulance",
        cluster_id="cluster-south",
        grid_row=8, grid_col=5,
        capacity=2.0,
        available=2.0,
        mobile=True,
        metadata={"unit": "patients", "crew_size": 2},
    ))

    # ── Hospital ──────────────────────────────────────────────────
    inventory.register(ResourceBase(
        resource_id="hospital-1",
        resource_type="hospital",
        cluster_id="cluster-south",
        grid_row=7, grid_col=9,
        capacity=50.0,
        available=42.0,
        mobile=False,
        metadata={"unit": "beds", "trauma_center": True},
    ))

    # ── Helicopter ────────────────────────────────────────────────
    inventory.register(ResourceBase(
        resource_id="heli-1",
        resource_type="helicopter",
        cluster_id="cluster-north",
        grid_row=0, grid_col=5,
        capacity=4.0,
        available=4.0,
        mobile=True,
        metadata={"unit": "flight_hours", "type": "Sikorsky S-70"},
    ))

    return inventory


def create_full_wildfire_scenario() -> Tuple[
    GenericWorldEngine[FireCellState], ResourceInventory
]:
    """
    Convenience function that returns both the engine and resource inventory.

    Use this when you want the complete scenario with preparedness assets.

    Returns:
        (engine, resource_inventory) tuple.
    """
    engine = create_basic_wildfire()
    resources = create_wildfire_resources(
        grid_rows=engine.grid.rows,
        grid_cols=engine.grid.cols,
    )
    return engine, resources
