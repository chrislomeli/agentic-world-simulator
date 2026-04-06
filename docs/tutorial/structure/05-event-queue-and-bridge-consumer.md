# Session 05: Event Queue + Bridge Consumer

## Goal
Wire the SensorEventQueue to an EventBridgeConsumer. Verify the async producer/consumer plumbing works with a logging callback before plugging in real agents.

## Rubric Skills Introduced
- None (infrastructure — no LangGraph yet)

## Key Concepts
- **SensorEventQueue** — async queue bridging publisher and consumer
- **EventBridgeConsumer** — pulls events, buffers by cluster_id, invokes agent when batch is full
- **Batching** — events accumulate per cluster until batch_size is reached
- **_invoke_agent()** — constructs initial state dict and calls `graph.invoke(state)`

## What You Build
1. A SensorEventQueue shared between publisher and consumer
2. An EventBridgeConsumer with a no-op or logging agent graph
3. Async pipeline: publisher.run() → queue → consumer.run()

## What You Can Run
```python
import asyncio
from domains.wildfire import create_basic_wildfire
from domains.wildfire.sensors import TemperatureSensor
from sensors import SensorPublisher
from transport import SensorEventQueue
from bridge.consumer import EventBridgeConsumer

engine = create_basic_wildfire()
queue = SensorEventQueue()

sensors = [
    TemperatureSensor(source_id="temp-1", cluster_id="cluster-north",
                      engine=engine, grid_row=3, grid_col=3),
]

publisher = SensorPublisher(sensors=sensors, queue=queue, engine=engine)

# Use a minimal stub graph (built in next session)
# For now, just verify events flow through
from agents.cluster.graph import build_cluster_agent_graph
stub_graph = build_cluster_agent_graph()  # stub mode

consumer = EventBridgeConsumer(
    queue=queue,
    agent_graph=stub_graph,
    batch_size=3,
)

async def main():
    await publisher.run(ticks=10)
    await consumer.run(max_events=queue.total_enqueued)
    print(f"Events consumed: {consumer.events_consumed}")
    print(f"Agent invocations: {consumer.invocations}")
    print(f"Findings: {len(consumer.collected_findings)}")

asyncio.run(main())
```

## Key Files
- `src/transport/queue.py` — SensorEventQueue
- `src/bridge/consumer.py` — EventBridgeConsumer

## Key Design Detail
The consumer constructs the LangGraph initial state explicitly in `_invoke_agent()`:
```python
state = {
    "cluster_id": cluster_id,
    "sensor_events": events,      # ← buffered events placed here
    "trigger_event": events[-1],  # ← most recent event
    "messages": [],
    "anomalies": [],
    "status": "idle",
}
result = self._agent_graph.invoke(state)
```

Events don't "stream" into the graph — they're batched by the consumer and passed as the initial state.

## Verification
- Publisher produces events, consumer consumes them
- Events are buffered per cluster_id
- Agent is invoked when batch_size is reached
- Remaining partial batches are flushed at the end

## Next Session
Session 06 builds the cluster agent graph that the consumer invokes.
