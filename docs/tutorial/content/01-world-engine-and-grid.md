# Episode 1, Session 1: The Simulated World

> **What we're building:** A terrain grid, typed cell states, a global environment, and a tick loop.
> **Why we need it:** Every sensor reading, every agent decision, every resource deployment in this system happens in response to something happening in the world. This session builds that world — the ground truth the agent will never see directly.
> **What you'll have at the end:** A running engine you can tick forward and inspect, with a snapshot of the world's state at every step.

---

## Why simulation?

If you want to test whether an agent responds well to a wildfire, you need a wildfire. But you also need to be able to run that wildfire hundreds of times, inject sensor failures, degrade resources, rewind to a specific moment, and compare what the agent *assessed* against what was *actually happening*.

A real fire doesn't give you any of that. A simulation does.

The other thing a simulation gives you is a clean separation between **ground truth** and **observation**. In a real emergency, an incident commander only knows what their sensors and scouts report — a noisy, incomplete, delayed picture. That's the same position we want our agent in. The simulation runs the actual fire physics; the agent only sees what its sensors emit. We'll maintain that separation throughout this entire tutorial.

This session builds the simulation layer. No sensors yet, no agents — just the world evolving on its own.

---

## The architecture at a glance

The simulation has four moving parts that compose together:

**`GenericTerrainGrid`** is a 2D grid of cells. Each cell holds a `CellState` — a typed Pydantic model that describes what that cell currently looks like. For wildfire, that means terrain type, fuel moisture, slope, and fire state. The grid doesn't know anything about fire; it just stores whatever cell state type you give it.

**`EnvironmentState`** holds global conditions that apply everywhere: temperature, humidity, wind speed and direction. The environment evolves each tick via a bounded random walk — temperature drifts, wind shifts, humidity responds inversely to temperature. It's not a weather model, but it produces realistic-feeling variation.

**`PhysicsModule`** is where the domain logic lives. Each tick it receives the current grid and environment and returns a list of `StateEvent` objects — instructions for which cells should change to which new states. Critically, the physics module *does not mutate cells directly*. It produces change descriptions, and the engine applies them. This is a design choice we'll come back to.

**`GenericWorldEngine`** is the orchestrator. Each tick: the environment evolves, the physics module runs, state events are applied to the grid, and a `GenericGroundTruthSnapshot` is recorded. The engine doesn't know what a fire is — it just drives the loop. All domain knowledge lives in the physics module and cell states.

This separation — engine vs. domain — is intentional. Sessions 01 and 02 introduce the fire domain. But the same engine could run a flood simulation, a power grid failure, or a hospital surge scenario. Only the cell states, environment, and physics module would change.

---

## Cell states: immutable by design

A `FireCellState` holds everything that describes one cell of terrain:

```python
class FireCellState(CellState):
    terrain_type: TerrainType = TerrainType.GRASSLAND
    vegetation: float = 0.5
    fuel_moisture: float = 0.3
    slope: float = 0.0
    fire_state: FireState = FireState.UNBURNED
    fire_intensity: float = 0.0
    fire_start_tick: Optional[int] = None
```

It's a Pydantic model, and we treat it as immutable. When a cell needs to change state — say, when it catches fire — we don't mutate the existing object. Instead we call `cell_state.ignited(tick=5, intensity=0.8)`, which returns a *new* `FireCellState` with the fire fields updated and everything else preserved. The original is untouched.

This is what makes the `StateEvent` pattern work cleanly. The physics module builds a list of `StateEvent(row=r, col=c, new_state=new_cell_state)` objects and returns them. The engine applies each one atomically. There's no partial-update problem, no threading concern, and it's easy to test: feed a cell state into a function, get a new cell state out, check it.

The `CellState` base class lives in `src/world/cell_state.py`. You won't need to touch it — it just requires subclasses to implement `summary_label()`, which the engine uses for logging and grid summary counts.

---

## The tick loop

Here's what happens when you call `engine.tick()`:

1. `environment.tick()` — weather takes a random step within its bounds
2. `physics.tick_physics(grid, environment, tick)` — domain rules run, returns `List[StateEvent]`
3. The engine applies each `StateEvent` to the grid
4. A `GenericGroundTruthSnapshot` is created and appended to `engine.history`

The snapshot contains the tick number, the current environment as a dict, a grid summary (cell counts by label), and a `domain_summary` from `physics.summarize()`. That last field is where domain-specific outputs live — for fire, that'll be the list of burning cells, fire intensity maps, and later the Rothermel physics metrics. More on that in Session 02.

You can also call `engine.run(ticks=N)` to run multiple ticks at once and get back the list of snapshots.

---

## The pre-built scenario

The wildfire domain ships with a pre-built scenario that sets up a realistic 10×10 grid:

```python
from domains.wildfire import create_basic_wildfire

engine = create_basic_wildfire()

for tick in range(30):
    snapshot = engine.tick()
    print(f"Tick {snapshot.tick}: {snapshot.grid_summary}")
```

The grid has a forested north, a dry grassland south, a rock ridge running through the middle (acting as a natural firebreak, with a gap at columns 6–7), a lake in the northwest corner, and an urban area in the southeast. Wind blows from the southwest. Fire is pre-ignited at cell (7, 2) in the dry southern grassland.

You don't need to build this yourself — the scenario function is there precisely so you can skip the setup and start working with a running world. When you need a custom scenario, `create_basic_wildfire()` is a good template to study.

The scenario code lives in `src/domains/wildfire/scenarios.py`. The sensor and resource setup functions there are not covered in this session — we'll get to those in sessions 03 and 11.

---

## What you should see

Running the tick loop against the basic scenario, you'll see grid summary counts shift as fire spreads:

```
Tick  0: {'UNBURNED': 99, 'BURNING': 1, 'BURNED': 0}
Tick  5: {'UNBURNED': 94, 'BURNING': 5, 'BURNED': 1}
Tick 10: {'UNBURNED': 87, 'BURNING': 8, 'BURNED': 5}
...
```

The counts are the raw output of `summary_label()` on each cell — whatever the cell state's label is, it gets counted. For fire states that's UNBURNED, BURNING, and BURNED.

At this point you're just watching numbers change. Session 02 adds the physics layer that makes those numbers meaningful — rate of spread, flame length, fireline intensity. That's when the simulation starts producing data the agent can actually reason about.

---

## Key files

- `src/world/generic_engine.py` — `GenericWorldEngine`, `GenericGroundTruthSnapshot`
- `src/world/generic_grid.py` — `GenericTerrainGrid`, `GenericCell`
- `src/world/cell_state.py` — `CellState` abstract base
- `src/world/physics.py` — `PhysicsModule` abstract base, `StateEvent` dataclass
- `src/domains/wildfire/cell_state.py` — `FireCellState`, `FireState`, `TerrainType`
- `src/domains/wildfire/environment.py` — `FireEnvironmentState`
- `src/domains/wildfire/scenarios.py` — `create_basic_wildfire()`

---

*Next: Session 02 plugs in the Rothermel fire physics model, so each tick produces not just a count of burning cells but a physically grounded picture of how fast the fire is moving, how intense it is, and what kind of resources could actually stop it.*
