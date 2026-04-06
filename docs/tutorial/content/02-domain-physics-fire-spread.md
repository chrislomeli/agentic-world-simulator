# Episode 1, Session 2: Fire That Behaves Like Fire

> **What we're building:** A physics-grounded fire spread model that replaces the probabilistic placeholder with Rothermel (1972) equations.
> **Why we need it:** Random-dice-roll fire spread can look like fire, but it can't produce numbers. Numbers are what the LLM supervisor will reason about in sessions 11–12. We need the simulation to tell us *how fast* the fire is moving, *how intense* it is, and *what kind of resources* could actually stop it.
> **What you'll have at the end:** A tick loop that prints rate of spread, fireline intensity, and danger rating alongside the cell counts — a simulation that has started generating operationally meaningful data.

---

## Why the placeholder isn't enough

Session 01 gave us a world that runs. Fire starts in the dry southern grassland, spreads to neighboring cells, and eventually burns out. The output looks like this:

```
Tick  0: {'UNBURNED': 99, 'BURNING': 1, 'BURNED': 0}
Tick  5: {'UNBURNED': 94, 'BURNING': 5, 'BURNED': 1}
Tick 10: {'UNBURNED': 87, 'BURNING': 8, 'BURNED': 5}
```

Those are counts. They show *that* fire is spreading, not *how*. The underlying physics module — `SimpleFirePhysicsModule` — works by rolling dice: a burning cell has a 15% chance per tick of igniting each unburned neighbor. That's it. No wind. No moisture. No terrain. No fuel type. Just a flat probability.

That's fine for a placeholder. It's not fine for an agent.

When we get to the supervisor agent in Session 10, we want it to be able to say something like: "Fireline intensity in cluster-south is 450 BTU/ft/s — that's in the engine suppression range, but I'm showing only one engine-type resource available there." For that sentence to be possible, the simulation has to produce numbers that map onto real operational categories. Random dice don't produce those numbers. Physics does.

---

## The Rothermel model in one paragraph

Richard Rothermel published his fire spread model for the US Forest Service in 1972. The core idea: a fire's rate of spread (ROS, in ft/min) is a function of the fuel it's burning through, the moisture content of that fuel, the wind that's carrying heat into unburned fuel ahead, and the slope of the terrain. The basic form is:

```
ROS = R₀ × rh_factor × moisture_factor × temp_factor × wind_factor × slope_factor
```

Where `R₀` is the base spread rate for that fuel type (a physical constant — grassland burns faster than dense forest), and the remaining factors are multipliers that can amplify or suppress it. High temperature, low humidity, dry fuel, strong tailwind, and uphill slope all amplify spread. Wet fuel, calm conditions, and flat terrain suppress it.

The model is simplified here — a full implementation would include surface-area-to-volume ratios, packing ratios, mineral content, and wind adjustment functions that fill a 50-page report. We're implementing enough physics to produce meaningful operational numbers, not enough to certify a prescribed burn.

---

## Fuel models: terrain type as fire fuel

The Rothermel formula needs to know what kind of fuel a cell is burning. That means translating our `TerrainType` enum into physical parameters. That's what `fuel_models.py` does.

Each terrain type maps to a `FuelModel` with:

- **`base_spread_rate_ft_min`** — how fast fire spreads through this fuel type in neutral conditions. Grassland (18 ft/min) burns much faster than dense forest (6 ft/min) because the fuel is fine and the spacing lets air reach it.
- **`heat_content_btu_lb`** — energy released per pound of fuel burned. This is what drives fireline intensity.
- **`moisture_of_extinction`** — the fuel moisture level at which fire stops sustaining itself.

Rock and water have no fuel model. If a cell has no fuel model, the physics module treats it as non-burnable, which is exactly right — you don't need to encode "rock doesn't burn" anywhere else in the system.

```python
FUEL_MODELS = {
    TerrainType.GRASSLAND: FuelModel(base_spread_rate_ft_min=18.0, heat_content_btu_lb=8000.0, ...),
    TerrainType.SCRUB:     FuelModel(base_spread_rate_ft_min=12.0, heat_content_btu_lb=9500.0, ...),
    TerrainType.FOREST:    FuelModel(base_spread_rate_ft_min=6.0,  heat_content_btu_lb=8500.0, ...),
    TerrainType.URBAN:     FuelModel(base_spread_rate_ft_min=8.0,  heat_content_btu_lb=9000.0, ...),
    # ROCK and WATER absent — non-burnable
}
```

This is a lookup, not logic. If you want to add a new terrain type, you add a fuel model entry. The physics module doesn't need to change.

---

## What the physics module actually does each tick

`RothermelFirePhysicsModule` is the drop-in replacement for `SimpleFirePhysicsModule`. It implements the same `PhysicsModule` interface: `tick_physics(grid, environment, tick)` returns a list of `StateEvent` objects. The engine doesn't know or care what's inside it.

Here's what happens per burning cell each tick:

**1. Compute heading ROS.** Pull the fuel model for this cell's terrain type. Compute environmental factors from the current `FireEnvironmentState` (temperature, humidity, wind speed). Apply moisture and vegetation. The result is the fire's maximum spread rate — the "heading" rate, fully into the wind.

**2. Update metrics.** The ROS drives two derived quantities, both from Byram (1959):

```
flame_length_ft = (ROS × heat_content / 500) ^ 0.46
fireline_intensity = (ROS / 60.0) × heat_content × moisture_factor × 0.9
```

Flame length tells you how tall the fire is. Fireline intensity (BTU/ft/s) tells you how much energy the fire is releasing per second per foot of fireline. These are the numbers that determine suppression feasibility — hand crews can work fires below about 100 BTU/ft/s; above 2000, only aircraft have any effect.

Note the `/ 60.0` in the intensity formula. ROS is measured in ft/min, but Byram's formula needs ft/s. Miss that conversion and you get intensities that are 60× too large — well outside any physically meaningful range.

**3. Check burn duration.** A cell burns for `burn_duration_ticks` (default 5 ticks = 25 simulated minutes) before extinguishing. When it extinguishes, all metrics zero out and the cell state becomes `BURNED`.

**4. Try to ignite neighbors.** For each unburned, burnable neighbor, compute the directional ROS. This is where wind becomes directional rather than scalar: the effective wind component for a given spread direction is the dot product of the wind unit vector with the spread direction vector.

```python
wind_alignment = wind_row * dr_n + wind_col * dc_n
effective_wind_mph = max(0.0, wind_mph * wind_alignment)
```

A cell spreading downwind (alignment ≈ 1.0) gets full wind amplification. A cell spreading crosswind (alignment ≈ 0.0) gets none. Backing fire (alignment < 0) is clamped to zero — it can still spread at the base rate, but without wind boost. This is why wind direction matters: fire in a southwest wind will run hard toward the northeast and barely creep toward the southwest.

**5. Convert ROS to probability.** Here's the bridge between the continuous physics and the discrete cellular automaton:

```python
spread_distance_ft = ROS × time_step_min    # how far fire travels this tick
prob = min(0.95, spread_distance_ft / cell_size_ft)
```

With default settings (200 ft cells, 5 min ticks), a grassland ROS of 8 ft/min means 40 ft of travel in one tick — a 20% chance of crossing into the neighboring cell. A higher ROS (say 20 ft/min) means 100 ft of travel — 50% probability. Extreme conditions can push probability to the 0.95 cap.

This isn't random anymore in the same sense as the placeholder. The dice are still there — fire spread is stochastic — but the dice are loaded by physics. High ROS loads the dice heavily; low ROS barely loads them at all. The randomness captures the micro-scale variability (pockets of dry fuel, local wind eddies) while the physics captures the macro-scale behavior.

---

## Per-cell metrics on `FireCellState`

The three Rothermel metrics are stored directly on the cell state:

```python
class FireCellState(CellState):
    # ... existing fields ...
    rate_of_spread_ft_min: float = 0.0
    flame_length_ft: float = 0.0
    fireline_intensity_btu_ft_s: float = 0.0
```

They're updated every tick for every burning cell. When a cell ignites, it receives the metrics computed for it at the moment of ignition. When a cell extinguishes, all three zero out.

These fields are what the resource tools in Session 12 will query. The supervisor agent won't walk the grid looking for fire — it'll call `get_fire_behavior()`, which reads the `domain_summary` built from these per-cell values. The data flows: cell state → domain summary → tool response → LLM reasoning.

---

## The domain summary

Each tick, the engine calls `physics.summarize(grid)` and stores the result in `snapshot.domain_summary`. For the Rothermel module, that summary looks like this:

| Field | Units | What it tells you |
|-------|-------|-------------------|
| `burning_cells` | list of (row, col) | Positions of all currently burning cells |
| `fire_intensity_map` | 2D float | Per-cell intensity 0–1 (for visualization) |
| `cell_summary` | dict | Count by state: UNBURNED / BURNING / BURNED |
| `avg_ros_ft_min` | ft/min | Mean Rate of Spread across burning cells |
| `max_ros_ft_min` | ft/min | Peak Rate of Spread |
| `avg_flame_length_ft` | ft | Mean flame length |
| `max_fireline_intensity` | BTU/ft/s | Peak fireline intensity |
| `estimated_acres_hr` | acres/hr | Area growth rate (Anderson 1983 ellipse model) |
| `danger_rating` | string | Low / Moderate / High / Very High / Extreme |

The `danger_rating` tiers are derived from peak ROS as a fraction of 40 ft/min (the reference maximum). A grassland fire with favorable wind will push well into "High" or "Very High"; a slow-moving forest fire in humid conditions will sit at "Low" or "Moderate."

---

## Running it

The pre-built scenario defaults to Rothermel:

```python
from domains.wildfire import create_basic_wildfire

engine = create_basic_wildfire()  # use_rothermel=True by default

for tick in range(30):
    snapshot = engine.tick()
    burning = snapshot.grid_summary.get("BURNING", 0)
    burned  = snapshot.grid_summary.get("BURNED", 0)
    fb = snapshot.domain_summary
    print(
        f"Tick {snapshot.tick:2d}: {burning} burning, {burned} burned | "
        f"ROS={fb.get('avg_ros_ft_min', 0):.1f} ft/min  "
        f"intensity={fb.get('max_fireline_intensity', 0):.0f} BTU/ft/s  "
        f"danger={fb.get('danger_rating', 'N/A')}"
    )
```

You should see output like:

```
Tick  0:  1 burning,  0 burned | ROS=8.3 ft/min  intensity=455 BTU/ft/s  danger=Moderate
Tick  5:  5 burning,  1 burned | ROS=9.1 ft/min  intensity=498 BTU/ft/s  danger=Moderate
Tick 10:  8 burning,  5 burned | ROS=8.7 ft/min  intensity=477 BTU/ft/s  danger=Moderate
```

The fire starts in dry southern grassland and the initial intensity lands in the engine suppression range (100–500 BTU/ft/s). As it moves into other terrain types and weather varies, you'll see the numbers shift. When fire hits the rock ridge, it stalls. When it finds the gap in the ridge, it pushes through into the forest, where ROS drops (forest burns slower) but intensity may increase (forest has higher heat content per pound of fuel).

If you want to compare against the placeholder:

```python
engine = create_basic_wildfire(use_rothermel=False)
```

The cell counts will look roughly similar — fire still spreads and burns out. But `domain_summary` won't contain the Rothermel fields. You're back to dice.

---

## What this session unlocks

After Session 01, the engine produces: counts.

After Session 02, the engine produces: counts, rate of spread, flame length, fireline intensity, estimated acres per hour, and danger rating — updated every tick, per burning cell, available in the snapshot history.

That's the data budget. Sessions 03–05 build the sensor layer, which samples a noisy view of this ground truth. Sessions 06–10 build the agents, which reason about what the sensors report. Sessions 11–12 build the resource tools, which query this domain summary directly to assess preparedness.

When the supervisor agent eventually calls `get_fire_behavior()` and reads back "danger_rating: Very High, max_fireline_intensity: 1340 BTU/ft/s," it's reading numbers that came from here — from the Rothermel equations running on each burning cell each tick. The chain from physics to agent reasoning is direct. That's the design.

---

## Key files

- `src/domains/wildfire/rothermel_physics.py` — `RothermelFirePhysicsModule`: ROS computation, spread probability, flame length, fireline intensity, summarize()
- `src/domains/wildfire/fuel_models.py` — `FuelModel` dataclass, `FUEL_MODELS` lookup by `TerrainType`
- `src/domains/wildfire/cell_state.py` — `FireCellState` with Rothermel metric fields
- `src/domains/wildfire/physics.py` — `SimpleFirePhysicsModule` (original placeholder, `FirePhysicsModule` alias for backward compatibility)
- `src/domains/wildfire/scenarios.py` — `create_basic_wildfire(use_rothermel=True/False)`
- `docs/tutorial/wildfires/wirldfire-logic.md` — full Rothermel formula reference

---

*Next: Session 03 adds sensors. Until now, there's nothing between the simulation and your print statement — you can see everything exactly as it is. Session 03 introduces the separation that makes this interesting: noisy, incomplete, delayed observations of the ground truth, the same view an actual incident commander would have.*
