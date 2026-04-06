# Session 01: World Engine + Grid

## Goal
Build a terrain grid, define cell states, configure an environment, and run the tick loop. No sensors, no agents — just the world.

## Rubric Skills Introduced
- None (infrastructure — no LangGraph yet)

## Key Concepts
- **TerrainGrid** — 2D grid of GenericCell objects, each holding a typed CellState
- **CellState** — abstract base (Pydantic model) with `summary_label()` for logging
- **EnvironmentState** — global conditions (temperature, humidity, wind) that affect physics
- **PhysicsModule** — abstract base that applies rules each tick
- **GenericWorldEngine** — orchestrator: environment evolution → physics → snapshot

## What You Build
1. A `GenericTerrainGrid` with typed cells
2. An `EnvironmentState` subclass (e.g. `FireEnvironmentState`)
3. A `PhysicsModule` subclass (placeholder — real physics in Session 02)
4. A `GenericWorldEngine` that ticks and records `GenericGroundTruthSnapshot`

## What You Can Run
```python
from world.generic_engine import GenericWorldEngine
from world.terrain_grid import GenericTerrainGrid

# Build a 5×5 grid with default cells
# Configure environment and physics (placeholder)
engine = GenericWorldEngine(grid=grid, environment=env, physics=physics)

for tick in range(10):
    snapshot = engine.tick()
    print(f"Tick {snapshot.tick}: {snapshot.grid_summary}")
```

## Key Files
- `src/world/generic_engine.py` — GenericWorldEngine, GenericGroundTruthSnapshot
- `src/world/terrain_grid.py` — GenericTerrainGrid, GenericCell
- `src/world/cell_state.py` — CellState (abstract base)

## Verification
- Engine ticks without errors
- Snapshots contain tick number, environment dict, grid_summary
- Grid summary shows cell counts by label

## Next Session
Session 02 plugs in real fire physics so cells actually change state.
