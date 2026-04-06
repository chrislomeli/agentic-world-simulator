# Session 02: Domain Physics — Fire Spread

## Goal
Plug in the wildfire physics module, ignite a cell, and watch fire spread across the grid. Still no sensors or agents — just the world evolving.

## Rubric Skills Introduced
- None (infrastructure — no LangGraph yet)

## Key Concepts
- **FireCellState** — domain-specific cell state with fuel_type, intensity, burn status
- **FireEnvironmentState** — temperature, humidity, wind speed/direction
- **FirePhysicsModule** — spread rules based on fuel, wind, moisture
- **Pre-built scenarios** — `create_basic_wildfire()` returns a configured engine

## What You Build
1. A `FirePhysicsModule` wired into the engine
2. An initial ignition injected into the grid
3. A tick loop that prints the fire's progress

## What You Can Run
```python
from domains.wildfire import create_basic_wildfire

engine = create_basic_wildfire()

for tick in range(30):
    snapshot = engine.tick()
    burning = snapshot.grid_summary.get("BURNING", 0)
    burned = snapshot.grid_summary.get("BURNED", 0)
    print(f"Tick {snapshot.tick}: {burning} burning, {burned} burned")
```

## Key Files
- `src/domains/wildfire/cell_state.py` — FireCellState
- `src/domains/wildfire/environment.py` — FireEnvironmentState
- `src/domains/wildfire/physics.py` — FirePhysicsModule
- `src/domains/wildfire/scenarios.py` — create_basic_wildfire()

## Verification
- Fire starts at the ignition point and spreads
- Spread follows wind direction (south-west → north-east)
- Rock ridge acts as a firebreak
- Water cells don't burn
- Grid summary counts change each tick

## Next Session
Session 03 adds sensors so we can observe the fire through noisy readings.
