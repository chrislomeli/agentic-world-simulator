#!/usr/bin/env python3
"""
world_builder.py — STEP 02: World setup & sensors

Load a scenario from JSON and explore the world grid and sensor inventory.
This step has no agents, no pipeline — just the raw simulation state.

    WorldEngine  (wildfire grid + environment)
    SensorInventory  (sensors placed at grid positions, grouped by cluster)
    ResourceInventory  (response assets assigned to clusters)

After running this step you will be able to see:
  - The world grid rendered as ASCII art
  - Where each sensor sits on the grid
  - What a raw SensorEvent looks like before it enters the pipeline
"""

import asyncio

from domains.wildfire.sampler import sample_local_conditions
from domains.wildfire.scenario_loader import load_scenario_from_json
from examples.config_builder import configure_environment
from world.grid import FireState, TerrainType




# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: WORLD VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def render_grid(engine, inventory=None, layers=None):
    """
    Draw the world as ASCII art so we can see what's happening.

    Example output:
        0 T T T T T T T T T T
        1 T T T T T T T T T T
        2 T T t T T T T T T T    <- t is a temperature sensor
        3 T T T k T T T T T T    <- k is a smoke sensor
        ...

    Parameters:
        engine    : the world engine (provides grid state)
        inventory : optional SensorInventory — positions derived automatically
        layers    : optional list of source_type strings to show (e.g. ["smoke"]).
                    If None, all sensor types are shown.

    Legend:
        T = Forest (burns easily)
        . = Grassland
        # = Rock (won't burn)
        ~ = Water (won't burn)
        s = Scrub
        U = Urban
        F = Currently burning
        * = Already burned
        Sensor glyphs: t=temperature  k=smoke  h=humidity  w=wind  b=barometric  c=camera  +=overlap
    """
    # Glyph mapping: terrain type → character
    terrain = {
        TerrainType.FOREST: "T",
        TerrainType.GRASSLAND: ".",
        TerrainType.ROCK: "#",
        TerrainType.WATER: "~",
        TerrainType.SCRUB: "s",
        TerrainType.URBAN: "U",
    }

    # Sensor type → glyph
    sensor_glyph = {
        "temperature": "t",
        "smoke": "k",
        "humidity": "h",
        "wind": "w",
        "barometric_pressure": "b",
        "thermal_camera": "c",
    }

    # Build a position → glyph map from the inventory
    sensor_positions = {}  # (row, col) → glyph
    if inventory is not None:
        show_types = set(layers) if layers else inventory.layer_types()
        for stype in show_types:
            for pos in inventory.layer_positions(stype):
                rc = (pos[0], pos[1])  # project to 2D for rendering
                if rc in sensor_positions:
                    sensor_positions[rc] = "+"  # overlap
                else:
                    sensor_positions[rc] = sensor_glyph.get(stype, "?")

    rows = []
    # For each row in the grid
    for row_idx in range(engine.grid.rows):
        row = []
        # For each column in the grid
        for col_idx in range(engine.grid.cols):
            cell = engine.grid.get_cell(row_idx, col_idx)
            state = cell.cell_state

            # Decide what character to draw
            if state.fire_state == FireState.BURNING:
                glyph = "F"  # On fire now
            elif state.fire_state == FireState.BURNED:
                glyph = "*"  # Already burned
            elif (row_idx, col_idx) in sensor_positions:
                glyph = sensor_positions[(row_idx, col_idx)]
            else:
                glyph = terrain.get(state.terrain_type, "?")  # Terrain type

            row.append(glyph)

        rows.append(" ".join(row))

    # Print with column numbers on top
    print("  " + " ".join(str(col) for col in range(engine.grid.cols)))
    for idx, row in enumerate(rows):
        print(f"{idx} {row}")
    print()
    print("Legend: T=Forest  .=Grass  #=Rock  ~=Water  s=Scrub  U=Urban  F=Burning  *=Burned")
    print("Sensors: t=temp  k=smoke  h=humidity  w=wind  b=barometric  c=camera  +=overlap")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: WORLD SETUP
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    """
    Load a scenario and inspect the world + sensor state.

    Flow:
    1. Configure environment (API keys, logging)
    2. Load scenario (world engine, sensors, resources) from JSON
    3. Render the world grid with sensor positions
    4. Show a sample SensorEvent to illustrate the data model
    """

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 1: INITIALIZE
    # ───────────────────────────────────────────────────────────────────────────

    settings = configure_environment()

    # creat a world map with sensors and resources
    engine, sensor_inventory, resource_inventory = load_scenario_from_json(settings.world_data)
    sensors = sensor_inventory.all_sensors()
    resources = resource_inventory.all_resources()

    print(f"Created {len(sensors)} sensors across 2 clusters:")
    for sensor in sensors:
        print(f"  {sensor.source_id:12s}  cluster={sensor.cluster_id}  at ({sensor.grid_row}, {sensor.grid_col})")
    print(f"Sensor layers: {sensor_inventory.layer_types()}")
    print()
    print("--- World with sensor positions ---")
    render_grid(engine, inventory=sensor_inventory)

    # Show what a sensor event looks like (with sampled conditions)
    sample_conditions = sample_local_conditions(engine, sensors[5].grid_row, sensors[5].grid_col)
    sample_event = sensors[5].emit(sample_conditions)
    print("Raw SensorEvent:")
    print(f"  event_id:    {sample_event.event_id}")
    print(f"  source_id:   {sample_event.source_id}")
    print(f"  source_type: {sample_event.source_type}")
    print(f"  cluster_id:  {sample_event.cluster_id}")
    print(f"  sim_tick:    {sample_event.sim_tick}")
    print(f"  confidence:  {sample_event.confidence}")
    print(f"  payload:     {sample_event.payload}")

    print(f"Grid: {engine.grid.rows}×{engine.grid.cols}")
    print(
        f"Weather: {engine.environment.temperature_c}°C, "
        f"{engine.environment.humidity_pct}% humidity, "
        f"{engine.environment.wind_speed_mps} m/s wind"
    )
    print(f"Fire state: {engine.grid.summary_counts()}")
    print("--- Initial world state ---")
    render_grid(engine)
# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # asyncio.run() starts the async event loop and runs main()
    asyncio.run(main())
