"""
examples/wildfire_demo.py

End-to-end demo: world engine → sensors → SensorEvent envelopes.

What this demonstrates
───────────────────────
  1. The world engine ticks forward, evolving weather and fire spread.
  2. Sensors sample from the engine's state and produce SensorEvent envelopes.
  3. The agent would normally receive these envelopes via Kafka / event queue.
  4. Ground truth is recorded but NOT visible to the "agent side."

This is the proof that the full pipeline works:
  WorldEngine (ground truth) → Sensors (sample + noise) → SensorEvent → [agent]

Run with:
  python examples/wildfire_demo.py

Expected output:
  - Tick-by-tick summaries showing fire spread
  - Sensor readings that correlate with the fire (temperature spikes near
    burning cells, smoke increasing downwind)
  - A simple ASCII map showing the fire state at key moments
"""

import random
import sys
from pathlib import Path

# Add src/ to path when running directly (not needed with pip install -e .)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ogar.world.scenarios.wildfire_basic import create_basic_wildfire
from ogar.sensors.world_sensors import (
    TemperatureSensor,
    HumiditySensor,
    WindSensor,
    SmokeSensor,
    BarometricSensor,
    ThermalCameraSensor,
)
from ogar.world.grid import FireState


def print_grid(engine, tick: int) -> None:
    """
    Print a simple ASCII map of the grid showing fire state.

    Legend:
      .  = unburned
      *  = burning
      #  = burned out
      ~  = water
      ^  = rock
      U  = urban
    """
    symbols = {
        FireState.UNBURNED: ".",
        FireState.BURNING:  "*",
        FireState.BURNED:   "#",
    }
    print(f"\n  Grid at tick {tick}:")
    print(f"  {'  '.join(str(c) for c in range(engine.grid.cols))}")
    for r in range(engine.grid.rows):
        row_str = []
        for c in range(engine.grid.cols):
            cell = engine.grid.get_cell(r, c)
            from ogar.world.grid import TerrainType
            if cell.terrain_type == TerrainType.WATER:
                row_str.append("~")
            elif cell.terrain_type == TerrainType.ROCK:
                row_str.append("^")
            elif cell.terrain_type == TerrainType.URBAN and cell.fire_state == FireState.UNBURNED:
                row_str.append("U")
            else:
                row_str.append(symbols.get(cell.fire_state, "?"))
        print(f"  {'  '.join(row_str)}  | row {r}")
    print()


def run_demo():
    # ── Reproducibility ───────────────────────────────────────────
    # Seed the RNG so the scenario plays out the same way every time.
    # Change the seed to see different fire spread patterns.
    random.seed(42)

    # ── Create the scenario ───────────────────────────────────────
    engine = create_basic_wildfire()

    # ── Create sensors attached to the engine ─────────────────────
    # These sensors sample from the engine's state whenever read() is called.

    # Temperature sensor placed at (6, 4) — in the grassland,
    # near the initial ignition at (7, 2).
    temp_sensor = TemperatureSensor(
        engine=engine,
        grid_row=6,
        grid_col=4,
        noise_std=0.5,
        source_id="temp-south-central",
        cluster_id="cluster-south",
    )

    # Humidity sensor — reads global weather humidity.
    humidity_sensor = HumiditySensor(
        engine=engine,
        noise_std=1.0,
        source_id="humidity-south",
        cluster_id="cluster-south",
    )

    # Wind sensor — reads global wind speed and direction.
    wind_sensor = WindSensor(
        engine=engine,
        speed_noise_std=0.3,
        direction_noise_std=3.0,
        source_id="wind-south",
        cluster_id="cluster-south",
    )

    # Smoke sensor placed at (5, 6) — downwind of the ignition point.
    # Should see rising PM2.5 as fire spreads toward it.
    smoke_sensor = SmokeSensor(
        engine=engine,
        grid_row=5,
        grid_col=6,
        noise_std=2.0,
        source_id="smoke-south-east",
        cluster_id="cluster-south",
    )

    # Barometric pressure — reads global weather pressure.
    baro_sensor = BarometricSensor(
        engine=engine,
        noise_std=0.3,
        source_id="baro-south",
        cluster_id="cluster-south",
    )

    # Thermal camera covering the southern grassland (rows 5-9, cols 0-9).
    thermal_camera = ThermalCameraSensor(
        engine=engine,
        top_row=5,
        left_col=0,
        view_rows=5,
        view_cols=10,
        noise_std=1.0,
        source_id="thermal-south",
        cluster_id="cluster-south",
    )

    sensors = [temp_sensor, humidity_sensor, wind_sensor, smoke_sensor, baro_sensor, thermal_camera]

    # ── Run the simulation ────────────────────────────────────────
    print("=" * 70)
    print("  WILDFIRE DEMO — World Engine + Sensors")
    print("=" * 70)
    print()
    print("  Grid: 10x10 | Fire starts at (7,2) | Wind: SW at 8 m/s")
    print("  Sensors: temp, humidity, wind, smoke, barometric, thermal camera")
    print()

    # Show initial grid state.
    print_grid(engine, tick=0)

    # Run for 20 ticks, printing sensor readings at key intervals.
    for t in range(20):
        # Tick the engine — weather evolves, fire spreads.
        snapshot = engine.tick()

        # Print sensor readings every 5 ticks (and on tick 0 and 1).
        if t in (0, 1, 5, 10, 15, 19):
            print(f"--- Tick {t} ---")
            print(f"  Weather: {engine.weather}")
            print(f"  Fire:    {snapshot.cell_summary}")

            # Emit sensor events (this is what the agent would receive).
            for sensor in sensors:
                event = sensor.emit()
                if event is None:
                    print(f"  {sensor.source_id}: DROPOUT (no reading)")
                    continue

                # Print a compact version of the event.
                # In the real system, this goes to Kafka / event queue.
                if sensor.source_type == "thermal_camera":
                    # Don't print the full grid — just summarise.
                    grid_data = event.payload.get("grid_celsius", [])
                    max_temp = max(max(row) for row in grid_data) if grid_data else 0
                    min_temp = min(min(row) for row in grid_data) if grid_data else 0
                    print(
                        f"  {sensor.source_id}: thermal grid — "
                        f"min={min_temp:.1f}°C max={max_temp:.1f}°C "
                        f"(conf={event.confidence:.2f})"
                    )
                else:
                    print(
                        f"  {sensor.source_id}: {event.payload} "
                        f"(conf={event.confidence:.2f})"
                    )

            print_grid(engine, tick=t)

    # ── Final summary ─────────────────────────────────────────────
    print("=" * 70)
    print("  SCENARIO COMPLETE")
    print("=" * 70)
    final = engine.grid.summary()
    print(f"  Final grid state: {final}")
    print(f"  Total ticks: {engine.current_tick}")
    print(f"  Ground truth snapshots recorded: {len(engine.history)}")
    print()
    print("  In the full system, these sensor events would flow to Kafka,")
    print("  through the bridge consumer, to the cluster agent LangGraph,")
    print("  and the agent would decide what to do about the fire.")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
