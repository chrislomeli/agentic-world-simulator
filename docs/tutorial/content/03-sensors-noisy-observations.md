# Episode 1, Session 3: The View From the Sensors

> **What we're building:** Sensor subclasses that sample the simulation grid and emit noisy, incomplete observations.
> **Why we need it:** The agent can't see the ground truth. It only knows what its sensors report. This session builds that separation — the core insight that makes this a testbed rather than just a simulation.
> **What you'll have at the end:** Sensors placed on the grid that produce readings you can compare to actual cell states, showing exactly how much information is lost between reality and observation.

---

## Why sensors matter

Sessions 01–02 gave you a simulation that runs and produces physics-grounded fire metrics. You can print the grid summary, inspect any cell's state, and see the exact rate of spread and fireline intensity at every burning cell. You have perfect information.

An incident commander doesn't.

An incident commander has weather stations that report every 10 minutes, smoke sensors that drift out of calibration, thermal cameras with blind spots, and scouts radioing in observations from positions they may or may not report accurately. The picture is noisy, incomplete, delayed, and sometimes wrong.

That's the environment we want the agent in. Not because we're trying to make its job harder, but because that's the environment where we need to know if it works. If the agent only functions with perfect information, it's not useful. If it can assess a situation and make good decisions with the same incomplete view a human incident commander has, then we've built something that might actually help.

This session builds the sensor layer — the boundary between what's actually happening (ground truth) and what the agent can observe (sensor events). Everything after this session operates on the observation side of that boundary. The agent will never call `engine.grid.get_cell()`. It will only see `SensorEvent` objects.

---

## The architecture: sensors produce events, not data

A sensor is a device with a location that samples the world and emits events. The design has three pieces:

**`SensorBase`** is an abstract base class. Subclasses implement one method: `read() → dict`. That method returns a plain dict with the sensor's current reading — temperature in Celsius, smoke density in µg/m³, whatever the sensor measures. The base class wraps that dict in a `SensorEvent` envelope, applies failure modes, tracks the simulation tick, and returns the envelope. Subclasses never touch the envelope.

**`SensorEvent`** is the canonical transport envelope. It's a Pydantic model with routing fields (`source_id`, `cluster_id`), timing fields (`timestamp`, `sim_tick`), a trust field (`confidence`), and an opaque `payload` dict. The envelope knows *how to route* an event and *how much to trust it*, but it doesn't know *what the reading means*. All domain-specific meaning lives in `payload`. This separation means you can add new sensor types without changing the envelope schema.

**Domain sensor subclasses** live in `domains/wildfire/sensors.py`. Each one holds a reference to the engine and queries it during `read()`. `TemperatureSensor` reads ambient temperature from the environment and adds radiant heat from nearby burning cells. `SmokeSensor` computes PM2.5 based on fire intensity, distance, and wind direction. `ThermalCameraSensor` reads a 2D heat grid over a rectangular region. Each sensor adds Gaussian noise to its readings — the `noise_std` parameter controls how much.

The key insight: sensors don't return ground truth. They return *noisy samples* of ground truth. A temperature sensor at position (3, 3) doesn't return `cell_state.fire_intensity`. It returns `ambient_temp + radiant_heat_from_neighbors + gaussian_noise`. The agent will see the noisy reading. You, looking at the grid, can see both and measure the gap.

---

## SensorBase: the contract

Here's what `SensorBase` requires from subclasses:

```python
class TemperatureSensor(SensorBase):
    source_type = "temperature"  # ← class-level string tag
    
    def read(self) -> Dict[str, Any]:
        # Return a plain dict — the base class wraps it
        return {"celsius": 42.1, "unit": "C"}
```

That's it. Two things: a `source_type` string and a `read()` method. The base class handles everything else:

- **Envelope construction** — `emit()` calls `read()`, wraps the result in a `SensorEvent`, and returns it.
- **Tick tracking** — the base class increments an internal tick counter each time `emit()` is called, so the event knows which simulation step it came from.
- **Failure modes** — if the sensor is in `DROPOUT` mode, `emit()` returns `None`. If it's in `STUCK` mode, `emit()` returns the same reading every call. The subclass never sees this — it just implements `read()` as if the sensor were healthy.
- **Confidence scoring** — `health()` returns a float 0.0–1.0 based on the current failure mode. `NORMAL` → 1.0, `DRIFT` → 0.7, `STUCK` → 0.3. The confidence value goes into the event envelope.

This design keeps domain logic (how to compute a temperature reading from fire state) separate from transport logic (how to wrap that reading in an envelope and route it to the right agent).

---

## The SensorEvent envelope

Every sensor reading, regardless of type, gets wrapped in the same envelope:

```python
@dataclass
class SensorEvent:
    event_id: str           # UUID, unique per emission
    source_id: str          # "temp-sensor-A1" — stable sensor identifier
    source_type: str        # "temperature" — tells agents how to unpack payload
    cluster_id: str         # "cluster-north" — routing key for the bridge consumer
    timestamp: datetime     # UTC wall-clock time
    sim_tick: int           # Simulation tick counter (0 if not in simulation)
    confidence: float       # 0.0–1.0, sensor self-reported health
    payload: dict           # Opaque reading data — {"celsius": 42.1}
    metadata: dict          # Optional extras — grid position, firmware version, etc.
```

The envelope is domain-agnostic. It doesn't know what a temperature is or what PM2.5 means. It just carries the payload and provides routing and trust metadata. This is what crosses the wire between sensors and agents. The bridge consumer (Session 05) will read `cluster_id` to decide which agent gets the event. The agent will read `source_type` to know how to unpack `payload`. The envelope itself never inspects `payload`.

Grid position (`grid_row`, `grid_col`) is injected into `metadata` automatically by `SensorBase.emit()`, so downstream consumers can see where a reading came from without changing the envelope schema.

---

## TemperatureSensor: reading with noise

Here's how `TemperatureSensor` works:

```python
def read(self) -> Dict[str, Any]:
    env: FireEnvironmentState = self._engine.environment
    base_temp = env.temperature_c
    
    # Heat from nearby burning cells
    heat_boost = 0.0
    for nr, nc, _nl in self._engine.grid.neighbors(self.grid_row, self.grid_col):
        neighbor = self._engine.grid.get_cell(nr, nc)
        if neighbor.cell_state.fire_state == FireState.BURNING:
            heat_boost += neighbor.cell_state.fire_intensity * 15.0
    
    # Heat from own cell if burning
    own_cell = self._engine.grid.get_cell(self.grid_row, self.grid_col)
    if own_cell.cell_state.fire_state == FireState.BURNING:
        heat_boost += own_cell.cell_state.fire_intensity * 40.0
    
    noise = random.gauss(0, self._noise_std)
    celsius = base_temp + heat_boost + noise
    return {"celsius": round(celsius, 1), "unit": "C"}
```

The reading is: ambient temperature + radiant heat from neighbors + radiant heat from own cell + Gaussian noise. A sensor far from fire will report close to ambient (say 25°C). A sensor next to a burning cell will report elevated temperature (40–60°C). A sensor *in* a burning cell will spike (80°C+). The noise (default `noise_std=0.5`) means two sensors at the same position won't report identical values — there's always a small random offset.

This is not ground truth. Ground truth is `cell_state.fire_intensity`. The sensor reading is a *derived, noisy estimate* of nearby fire activity. The agent will see the reading and have to infer what's actually happening.

---

## SmokeSensor: distance, wind, and accumulation

`SmokeSensor` is more complex because smoke disperses with wind and distance:

```python
def read(self) -> Dict[str, Any]:
    env: FireEnvironmentState = self._engine.environment
    baseline_pm25 = 5.0  # Clean air baseline
    wind_row, wind_col = env.wind_vector()
    
    total_smoke = 0.0
    for cell in self._engine.grid.iter_cells():
        if cell.cell_state.fire_state != FireState.BURNING:
            continue
        
        # Distance from sensor to burning cell
        dr = self.grid_row - cell.row
        dc = self.grid_col - cell.col
        dist = math.sqrt(dr * dr + dc * dc)
        distance_factor = 1.0 / (1.0 + dist)
        
        # Wind alignment: smoke drifts downwind
        if dist > 0:
            dir_r, dir_c = dr / dist, dc / dist
            dot = wind_row * dir_r + wind_col * dir_c
            wind_factor = max(0.1, 0.5 + dot * 0.5)
        else:
            wind_factor = 1.0
        
        contribution = (
            cell.cell_state.fire_intensity
            * distance_factor * wind_factor * 80.0
        )
        total_smoke += contribution
    
    pm25 = baseline_pm25 + total_smoke + random.gauss(0, self._noise_std)
    return {"pm25_ugm3": round(pm25, 1), "unit": "µg/m³"}
```

The sensor walks every burning cell, computes a contribution based on fire intensity, distance, and wind alignment, and sums them. A sensor downwind of a fire will read higher PM2.5 than a sensor upwind at the same distance. A sensor far from all fire will read close to baseline (5 µg/m³). A sensor near intense fire will spike into the hundreds.

This is still not ground truth. Ground truth is the set of burning cells and their intensities. The sensor reading is a *spatial aggregation with wind bias and noise*. The agent will see a PM2.5 spike and have to infer where the fire is.

---

## Failure modes: testing agent resilience

Real sensors fail. `SensorBase` supports injecting failure modes so you can test whether the agent handles degraded observations:

- **`NORMAL`** — sensor works as implemented, `confidence=1.0`
- **`STUCK`** — sensor returns the same reading every call (frozen), `confidence=0.3`
- **`DROPOUT`** — sensor goes silent, `emit()` returns `None`, `confidence=0.0`
- **`DRIFT`** — gradual offset accumulates (not yet implemented), `confidence=0.7`
- **`SPIKE`** — occasional large outlier (not yet implemented), `confidence=0.5`

You set the mode externally:

```python
sensor.set_failure_mode(FailureMode.STUCK)
```

From that point, `emit()` applies the mode. If `DROPOUT`, it returns `None` without calling `read()`. If `STUCK`, it calls `read()` once, caches the result, and returns that cached payload on every subsequent call. The subclass doesn't know or care — it just implements `read()` as if the sensor were healthy.

The `confidence` field in the event envelope reflects the failure mode. An agent that pays attention to confidence can downweight or discard low-confidence readings. An agent that ignores confidence will be misled by stuck sensors. That's the test.

---

## Running it

Here's a minimal script that places a temperature sensor on the grid, ticks the engine, and compares sensor readings to ground truth:

```python
from domains.wildfire import create_basic_wildfire
from domains.wildfire.sensors import TemperatureSensor

engine = create_basic_wildfire()

temp_sensor = TemperatureSensor(
    source_id="temp-1",
    cluster_id="cluster-north",
    engine=engine,
    grid_row=7,  # Southern grassland, near the ignition point
    grid_col=2,
)

for tick in range(20):
    snapshot = engine.tick()
    event = temp_sensor.emit()
    
    if event:
        # Ground truth: actual cell state
        cell = engine.grid.get_cell(7, 2)
        actual_fire_state = cell.cell_state.fire_state.value
        actual_intensity = cell.cell_state.fire_intensity
        
        # Observation: what the sensor reports
        observed_temp = event.payload["celsius"]
        
        print(
            f"Tick {tick:2d}: "
            f"sensor={observed_temp:5.1f}°C (conf={event.confidence:.1f}) | "
            f"ground_truth: {actual_fire_state}, intensity={actual_intensity:.2f}"
        )
```

You should see output like:

```
Tick  0: sensor= 26.3°C (conf=1.0) | ground_truth: UNBURNED, intensity=0.00
Tick  5: sensor= 27.1°C (conf=1.0) | ground_truth: UNBURNED, intensity=0.00
Tick 10: sensor= 52.4°C (conf=1.0) | ground_truth: BURNING, intensity=0.85
Tick 15: sensor= 48.9°C (conf=1.0) | ground_truth: BURNING, intensity=0.78
Tick 20: sensor= 26.8°C (conf=1.0) | ground_truth: BURNED, intensity=0.00
```

The sensor starts near ambient (26°C), spikes when the cell ignites (50°C+), and drops back to ambient when the cell burns out. The spike doesn't match the intensity value exactly — it's a noisy estimate based on radiant heat. That's the gap between observation and reality.

Now inject a failure:

```python
temp_sensor.set_failure_mode(FailureMode.STUCK)
```

Run the same loop. The sensor will freeze at whatever reading it had when you set the mode, and `confidence` will drop to 0.3. The agent (when we build it in Session 06) will see a stuck sensor reporting the same temperature tick after tick while other sensors show the fire spreading. A good agent will notice the anomaly. A naive agent will be confused.

---

## What this session unlocks

After Session 02, the simulation produces ground truth: cell states, fire metrics, environment conditions.

After Session 03, you have sensors that produce observations: noisy, incomplete, sometimes-wrong readings that sample the ground truth.

The gap between the two is the testbed. You can measure how much information is lost. You can inject failures and see how observations degrade. You can compare what the agent *thinks* is happening (based on sensor events) to what's *actually* happening (based on the grid snapshot).

Sessions 04–05 build the plumbing to get sensor events into a queue and route them to agents. Sessions 06–10 build the agents that reason about those events. But the fundamental separation — ground truth vs. observation — is established here. Everything after this operates on the observation side.

---

## Key files

- `src/sensors/base.py` — `SensorBase` abstract class, `FailureMode` enum, `emit()` logic, failure mode application
- `src/transport/schemas.py` — `SensorEvent` envelope, factory method, field documentation
- `src/domains/wildfire/sensors.py` — `TemperatureSensor`, `SmokeSensor`, `HumiditySensor`, `WindSensor`, `BarometricSensor`, `ThermalCameraSensor`

---

*Next: Session 04 introduces `SensorInventory` to manage multiple sensors and `SensorPublisher` to drive them all each tick, emitting events into a queue. Until now you've been calling `sensor.emit()` manually. Session 04 automates that and adds scenario knobs for thinning sensors and injecting failures across the whole inventory.*
