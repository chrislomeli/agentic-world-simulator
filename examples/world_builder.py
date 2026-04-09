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
from examples.render import render_grid


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: WORLD SETUP
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

    # Load world map with sensors and resources
    engine, sensor_inventory, resource_inventory = load_scenario_from_json(settings.world_data)
    sensors = sensor_inventory.all_sensors()
    print(f"Created {len(sensors)} sensors across 2 clusters:")
    for sensor in sensors:
        print(f"  {sensor.source_id:12s}  cluster={sensor.cluster_id}  at ({sensor.grid_row}, {sensor.grid_col})")
    print(f"Sensor layers: {sensor_inventory.layer_types()}")
    print()

    # Show all three layers so you can see how the data is laid out
    render_grid(engine, sensor_inventory=sensor_inventory, resource_inventory=resource_inventory)

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
    print(f"Fire state: {engine.grid.summary_counts()}")
# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # asyncio.run() starts the async event loop and runs main()
    asyncio.run(main())
