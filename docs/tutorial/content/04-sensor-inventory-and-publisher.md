# Episode 1, Session 4: Managing the Sensor Network

> **What we're building:** A sensor inventory to manage multiple sensors, a publisher to drive them all each tick, and scenario knobs to thin coverage or inject failures.
> **Why we need it:** Session 03 showed you how one sensor works. Real scenarios have dozens of sensors. You need a way to manage them as a collection, control their density, inject failures in bulk, and measure coverage gaps. This session builds that management layer.
> **What you'll have at the end:** An automated publisher loop that ticks the world, emits all sensor events into a queue, and lets you experiment with degraded observation conditions — the testbed knobs you'll use in Sessions 14–15 to stress-test the agent.

---

## Why inventory and publisher matter

Session 03 gave you individual sensors. You placed a `TemperatureSensor` at position (7, 2), called `sensor.emit()` manually each tick, and compared the reading to ground truth. That's fine for understanding how one sensor works. It's not scalable.

A realistic wildfire scenario has:
- Temperature sensors at 15–20 positions across the grid
- Smoke sensors at 10–15 positions, often co-located with temperature
- Wind sensors at 5–10 positions (fewer because wind is more uniform)
- Humidity sensors at 3–5 positions (global environment, sparse coverage is fine)

That's 30–50 sensors. You don't want to instantiate them one by one, track their positions manually, and call `emit()` on each in a loop. You want a registry that knows where every sensor is, what type it is, and can answer questions like "which cells have no coverage?" or "how many temperature sensors are in cluster-north?"

You also want experimental knobs. The whole point of this testbed is to see how the agent performs under degraded conditions. That means:
- **Thinning sensors** — remove 50% of them to simulate sparse deployment, see if the agent's assessment quality degrades.
- **Injecting failures** — put 20% of sensors into `STUCK` mode, see if the agent notices and discounts their readings.
- **Measuring coverage** — quantify how much of the grid is observable vs. blind spots.

`SensorInventory` provides those knobs. `SensorPublisher` automates the tick loop so you don't have to manually call `emit()` on 50 sensors. Together they turn "a collection of sensors" into "a managed sensor network with experimental controls."

---

## SensorInventory: the registry

`SensorInventory` is a typed registry that tracks which sensors are placed at which grid positions. It's domain-agnostic — it works with any `SensorBase` subclass, whether the domain is wildfire, ocean, or power grid.

The core operations:

**Registration** — add a sensor at a specific (row, col, layer) position:

```python
inventory = SensorInventory(grid_rows=10, grid_cols=10)
inventory.register(temp_sensor, row=3, col=4)
inventory.register(smoke_sensor, row=3, col=4)  # co-located, fine
```

Multiple sensors can occupy the same cell. A temperature sensor and a smoke sensor at the same position is common — they're different instruments on the same tower.

**Queries** — find sensors by position, type, or ID:

```python
sensors_at_34 = inventory.get_sensors_at(row=3, col=4)
all_temp_sensors = inventory.get_layer("temperature")
coverage = inventory.coverage_ratio()  # 0.0–1.0, fraction of grid covered
```

**Experimental knobs** — thin the network or inject failures:

```python
inventory.thin(keep_fraction=0.5)  # remove 50% of sensors randomly
inventory.inject_bulk_failure(FailureMode.STUCK, fraction=0.2)  # 20% stuck
```

**Emission** — drive all sensors at once:

```python
events = inventory.emit_all()  # calls emit() on every sensor
```

The inventory doesn't know what a temperature is or what a fire is. It just knows: this sensor has this ID, lives at this position, and is of this type. All domain logic stays in the sensor subclasses.

---

## Why SensorInventory mirrors ResourceInventory

If you've read the system-retrieved memory about the resource design, you'll notice `SensorInventory` follows the same pattern as `ResourceInventory`:

- Both are registries of positioned entities (sensors or resources)
- Both support querying by type, position, and ID
- Both provide scenario knobs (thinning, failure injection, degradation)
- Both are domain-agnostic — the base class doesn't know about wildfires

The difference: sensors *produce* data (they emit events), resources *are* data (they're queryable state). That's why `SensorInventory` has `emit_all()` but `ResourceInventory` doesn't. The pattern is the same; the responsibility differs.

This is intentional design. The system has a small set of composable patterns (registries, inventories, publishers, consumers) that recur across different subsystems. Once you understand the inventory pattern here, you'll recognize it when you hit resources in Session 11.

---

## Coverage analysis: measuring blind spots

One of the key questions the testbed needs to answer is: how much of the world can the agent actually see?

`SensorInventory` provides coverage metrics:

```python
coverage = inventory.coverage_ratio()  # 0.0–1.0, overall coverage
temp_coverage = inventory.layer_coverage_ratio("temperature")
covered_cells = inventory.covered_cells()  # set of (row, col, layer) tuples
```

Coverage is the fraction of grid cells that have at least one sensor. A 10×10 grid has 100 cells. If 30 cells have sensors, coverage is 0.3 (30%). If you thin the inventory to 50% of sensors, coverage might drop to 0.15 — not all sensors were at unique positions, so removing half the sensors doesn't remove half the coverage.

This is the experimental variable. You can run the same scenario twice:
1. Full coverage (0.3) → agent produces assessment A
2. Thinned coverage (0.15) → agent produces assessment B

Compare A and B to ground truth. If assessment quality degrades significantly when coverage drops, you've quantified the agent's sensitivity to observation density. That's the kind of result you'd put in a paper or a demo.

---

## SensorPublisher: the async tick loop

`SensorPublisher` sits between the sensor inventory and the event queue. Its job:

1. Tick the world engine (if wired)
2. Call `emit()` on every sensor
3. Put each non-None event onto the queue
4. Wait for the tick interval, repeat

Here's the minimal setup:

```python
from sensors import SensorPublisher
from transport import SensorEventQueue

queue = SensorEventQueue()
publisher = SensorPublisher(
    inventory=inventory,
    queue=queue,
    engine=engine,
    tick_interval_seconds=0.5,  # 2 ticks per second
)

await publisher.run(ticks=20)  # run for exactly 20 ticks, then stop
```

The publisher is async because in a real system sensors would be I/O-bound (reading from hardware, network sockets, or a remote simulation). The async structure is already correct for when you swap in real I/O. In this mock setup the sensors are CPU-bound (random number generation), but the pattern doesn't change.

Each tick:
- If `engine` is provided, `engine.tick()` runs first, advancing the simulation
- Then `inventory.all_sensors()` is iterated, calling `emit()` on each
- Each event goes onto the queue via `await queue.put(event)`
- Sensors in `DROPOUT` mode return `None` — the publisher skips them silently
- After all sensors, the publisher sleeps for `tick_interval_seconds`

The tick interval controls simulation speed. Set it low (0.1s) for fast scenario testing. Set it to 1.0s for realistic demos. Set it to 5.0s if you want to watch the fire spread in slow motion.

---

## SensorEventQueue: the pre-Kafka transport

`SensorEventQueue` is a thin wrapper around `asyncio.Queue[SensorEvent]`. It decouples the publisher from the consumer (Session 05) and provides back-pressure.

```python
queue = SensorEventQueue(maxsize=100)
await queue.put(event)   # publisher side — blocks if queue is full
event = await queue.get()  # consumer side — blocks if queue is empty
queue.task_done()        # mark event processed
```

The queue is typed — it only accepts `SensorEvent` objects. This prevents accidentally putting the wrong thing on the queue, which would cause confusing errors downstream.

**Back-pressure:** If `maxsize` is set (e.g. 100), `put()` blocks when the queue is full. This means the publisher slows down rather than filling memory if the consumer can't keep up. In production Kafka would handle this via consumer lag monitoring. The pattern is the same.

**Why not Kafka yet?** Because we don't need it yet. Everything runs in one process for the demo. The architecture already separates concerns correctly:

```
sensors → queue → bridge consumer → agents
```

The "queue" is the only thing that changes when Kafka arrives. The bridge consumer (Session 05) reads from a queue interface. When we swap `SensorEventQueue` for a `KafkaConsumerWrapper`, the bridge code doesn't change. That's the design.

---

## Scenario knobs: thinning and failures

The inventory provides two primary experimental knobs:

**Thinning** — randomly remove sensors to simulate sparse deployment:

```python
removed = inventory.thin(keep_fraction=0.5)  # keep 50%, remove 50%
print(f"Removed {len(removed)} sensors")
print(f"Coverage before: 0.30, after: {inventory.coverage_ratio():.2f}")
```

Thinning is random. If you have 40 sensors and thin to 50%, you'll have ~20 left, but *which* 20 is random. This simulates real-world scenarios where budget constraints force sparse deployment.

**Failure injection** — apply a failure mode to a fraction of sensors:

```python
stuck = inventory.inject_bulk_failure(FailureMode.STUCK, fraction=0.2)
print(f"Set {len(stuck)} sensors to STUCK mode")
```

After this, 20% of sensors will return the same reading every tick. Their `confidence` field will drop to 0.3. The agent (when we build it in Session 06) will see stuck sensors and have to decide whether to trust them.

You can also inject failures on specific sensor types:

```python
inventory.inject_layer_failure("temperature", FailureMode.DRIFT, fraction=0.3)
```

This puts 30% of temperature sensors into `DRIFT` mode (gradual offset accumulation, not yet fully implemented). Smoke sensors are unaffected. This lets you test whether the agent can still assess fire spread when temperature data is degraded but smoke data is clean.

---

## Running it

Here's a complete script that sets up an inventory, runs the publisher, and inspects the queue:

```python
import asyncio
from domains.wildfire import create_basic_wildfire
from domains.wildfire.sensors import TemperatureSensor, SmokeSensor
from world.sensor_inventory import SensorInventory
from sensors import SensorPublisher
from transport import SensorEventQueue

engine = create_basic_wildfire()
queue = SensorEventQueue()

# Build inventory
inventory = SensorInventory(grid_rows=10, grid_cols=10)

# Add temperature sensors at 5 positions
for row, col in [(2, 2), (2, 7), (5, 5), (7, 2), (7, 7)]:
    sensor = TemperatureSensor(
        source_id=f"temp-{row}-{col}",
        cluster_id="cluster-north",
        engine=engine,
        grid_row=row,
        grid_col=col,
    )
    inventory.register(sensor, row=row, col=col)

# Add smoke sensors at 3 positions
for row, col in [(3, 3), (5, 5), (7, 7)]:
    sensor = SmokeSensor(
        source_id=f"smoke-{row}-{col}",
        cluster_id="cluster-north",
        engine=engine,
        grid_row=row,
        grid_col=col,
    )
    inventory.register(sensor, row=row, col=col)

print(f"Inventory: {inventory.size} sensors, coverage={inventory.coverage_ratio():.0%}")

# Run publisher for 10 ticks
publisher = SensorPublisher(
    inventory=inventory,
    queue=queue,
    engine=engine,
    tick_interval_seconds=0.1,  # fast for testing
)

asyncio.run(publisher.run(ticks=10))

print(f"Events enqueued: {queue.total_enqueued}")
print(f"Events waiting: {queue.qsize()}")
```

You should see output like:

```
Inventory: 8 sensors, coverage=8%
Events enqueued: 80
Events waiting: 80
```

8 sensors × 10 ticks = 80 events (assuming no sensors are in `DROPOUT` mode). All events are sitting in the queue, waiting for a consumer (Session 05) to pull them off.

Now experiment with thinning:

```python
inventory.thin(keep_fraction=0.5)
print(f"After thinning: {inventory.size} sensors, coverage={inventory.coverage_ratio():.0%}")
```

You'll see the sensor count drop to ~4 and coverage drop accordingly. Run the publisher again — you'll get ~40 events instead of 80.

---

## What this session unlocks

After Session 03, you had individual sensors that you drove manually.

After Session 04, you have:
- A managed sensor network with position tracking and type indexing
- Coverage metrics to quantify observation gaps
- Experimental knobs to thin sensors or inject failures in bulk
- An automated publisher loop that ticks the world and emits all events into a queue

The queue is the handoff point. The publisher puts events on one end. Session 05 builds the consumer that pulls events off the other end and routes them to agents.

Sessions 14–15 (evaluation and stress testing) will use these knobs heavily. You'll run the same scenario with full coverage vs. thinned coverage, with healthy sensors vs. degraded sensors, and compare the agent's assessment quality. The infrastructure for that comparison is built here.

---

## Key files

- `src/world/sensor_inventory.py` — `SensorInventory`: registration, queries, coverage analysis, thinning, failure injection
- `src/sensors/publisher.py` — `SensorPublisher`: async tick loop, drives sensors, enqueues events
- `src/transport/queue.py` — `SensorEventQueue`: typed async queue, back-pressure, pre-Kafka transport

---

*Next: Session 05 builds the consumer side — `EventBridgeConsumer` pulls events off the queue, batches them by cluster_id, and invokes the cluster agent graph. That's where events finally reach the agent. Until now you've been producing events and putting them in a queue. Session 05 is where something actually reads them.*
