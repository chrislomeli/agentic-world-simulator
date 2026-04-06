# Session 04: Sensor Inventory + Publisher

## Goal
Register multiple sensors in a SensorInventory, configure failure modes and coverage, then use SensorPublisher to emit all sensor events into a queue each tick. Still no agents.

## Rubric Skills Introduced
- None (infrastructure — no LangGraph yet)

## Key Concepts
- **SensorInventory** — registration, querying by type/position, thinning, failure injection, coverage analysis
- **SensorPublisher** — drives sensors each tick, emits events into a SensorEventQueue
- **Scenario knobs** — thin_sensors(), inject_failures() to test agent resilience later
- **Coverage** — which grid cells are observed vs. blind spots

## What You Build
1. A SensorInventory with multiple sensor types at various positions
2. A SensorPublisher that ticks the engine and emits all sensor events
3. Scenario knob experiments: thin sensors, inject failures

## What You Can Run
```python
from domains.wildfire import create_basic_wildfire
from domains.wildfire.sensors import TemperatureSensor, SmokeSensor
from sensors import SensorPublisher
from transport import SensorEventQueue

engine = create_basic_wildfire()
queue = SensorEventQueue()

sensors = [
    TemperatureSensor(source_id="temp-1", cluster_id="cluster-north",
                      engine=engine, grid_row=3, grid_col=3),
    SmokeSensor(source_id="smoke-1", cluster_id="cluster-north",
                engine=engine, grid_row=5, grid_col=5),
]

publisher = SensorPublisher(sensors=sensors, queue=queue, engine=engine)

import asyncio
asyncio.run(publisher.run(ticks=10))
print(f"Events in queue: {queue.total_enqueued}")
```

## Key Files
- `src/world/sensor_inventory.py` — SensorInventory
- `src/sensors/publisher.py` — SensorPublisher
- `src/transport/queue.py` — SensorEventQueue

## Verification
- All sensors emit events each tick
- Events appear in the queue with correct cluster_id routing
- Thinning reduces the number of active sensors
- Failure injection causes some sensors to drop readings

## Next Session
Session 05 adds the consumer side — pulling events off the queue asynchronously.
