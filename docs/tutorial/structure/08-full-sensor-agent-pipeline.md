# Session 08: Full Sensor→Agent Pipeline

## Goal
Wire publisher → queue → consumer → cluster agent into a single async pipeline. First end-to-end flow: world ticks produce sensor events that agents classify into findings.

## Rubric Skills Introduced
| Skill | Level | Section |
|-------|-------|---------|
| Compile + invoke / stream | foundational | 1. Graph Primitives |
| stream_mode — values vs updates vs debug | mid-level | 7. Streaming and Observability |
| LangSmith tracing | mid-level | 7. Streaming and Observability |

## Key Concepts
- **Pipeline stages** — world engine → sensors → queue → consumer → agent graph → findings
- **Async orchestration** — publisher.run() and consumer.run() are async
- **LangSmith tracing** — `LANGCHAIN_TRACING_V2=true` traces every graph invocation
- **Stream mode** — use `graph.stream()` instead of `invoke()` to see intermediate states

## What You Build
1. Create engine + sensors + queue + publisher
2. Create consumer with cluster agent graph
3. Run the async pipeline
4. Collect and inspect findings

## What You Can Run
```python
import asyncio
from domains.wildfire import create_basic_wildfire
from domains.wildfire.sensors import TemperatureSensor, SmokeSensor
from sensors import SensorPublisher
from transport import SensorEventQueue
from bridge.consumer import EventBridgeConsumer
from agents.cluster.graph import build_cluster_agent_graph

async def main():
    engine = create_basic_wildfire()
    queue = SensorEventQueue()

    sensors = [
        TemperatureSensor(source_id="temp-n1", cluster_id="cluster-north",
                          engine=engine, grid_row=3, grid_col=3),
        SmokeSensor(source_id="smoke-n1", cluster_id="cluster-north",
                    engine=engine, grid_row=5, grid_col=5),
    ]

    publisher = SensorPublisher(sensors=sensors, queue=queue, engine=engine)
    cluster_graph = build_cluster_agent_graph()  # stub or llm

    findings = []
    consumer = EventBridgeConsumer(
        queue=queue,
        agent_graph=cluster_graph,
        batch_size=5,
        on_finding=lambda f: findings.append(f),
    )

    await publisher.run(ticks=20)
    await consumer.run(max_events=queue.total_enqueued)

    print(f"Events: {consumer.events_consumed}")
    print(f"Invocations: {consumer.invocations}")
    print(f"Findings: {len(findings)}")
    for f in findings:
        print(f"  [{f['anomaly_type']}] {f['cluster_id']} — {f['summary'][:60]}")

asyncio.run(main())
```

## Observability

### LangSmith tracing
```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=your_key_here
python examples/pipeline_demo.py
```

### Stream mode (for debugging)
```python
# Instead of graph.invoke(state), use:
for node_name, state_update in graph.stream(state, stream_mode="updates"):
    print(f"Node: {node_name}, Updated: {list(state_update.keys())}")
```

## Key Files
- `examples/pipeline_demo_annotated.py` — complete reference implementation

## Verification
- Events flow from publisher through queue to consumer
- Consumer batches events and invokes agent at batch_size intervals
- Findings appear in the callback
- LangSmith shows the full trace (if enabled)

## Next Session
Session 09 adds the supervisor agent that correlates findings across clusters.
