# Session 03: Sensors — Noisy Observations

## Goal
Create sensor subclasses, place them on the grid, call `emit()`, and see how sensor readings differ from ground truth. No queue, no agents — just sensors producing events.

## Rubric Skills Introduced
- None (infrastructure — no LangGraph yet)

## Key Concepts
- **SensorBase** — abstract base class with `read()` → `emit()` → `SensorEvent`
- **SensorEvent** — canonical envelope: source_id, source_type, cluster_id, sim_tick, payload, confidence
- **Noise** — sensors add Gaussian noise to readings
- **Failure modes** — sensors can intermittently fail (drop readings, stuck values)
- **Ground truth vs. observation** — the core testbed insight

## What You Build
1. Instantiate TemperatureSensor and SmokeSensor from `domains.wildfire.sensors`
2. Place them at specific grid positions
3. Tick the engine, then call `sensor.emit()` to get SensorEvents
4. Compare readings to actual cell state (ground truth)

## What You Can Run
```python
from domains.wildfire import create_basic_wildfire
from domains.wildfire.sensors import TemperatureSensor, SmokeSensor

engine = create_basic_wildfire()

temp_sensor = TemperatureSensor(
    source_id="temp-1", cluster_id="cluster-north",
    engine=engine, grid_row=3, grid_col=3,
)

for tick in range(20):
    engine.tick()
    event = temp_sensor.emit()
    if event:
        actual = engine.grid.get_cell(3, 3).state.summary_label()
        print(f"Tick {tick}: sensor={event.payload} | ground_truth={actual}")
```

## Key Files
- `src/sensors/base.py` — SensorBase, emit(), failure modes
- `src/transport/schemas.py` — SensorEvent envelope
- `src/domains/wildfire/sensors.py` — TemperatureSensor, SmokeSensor

## Verification
- Sensor readings have noise (not exact ground truth values)
- Confidence field reflects sensor health
- Occasional failures produce None or degraded readings
- Fire approaching sensor position causes temperature spike in readings

## Next Session
Session 04 manages multiple sensors with SensorInventory and publishes events to a queue.
