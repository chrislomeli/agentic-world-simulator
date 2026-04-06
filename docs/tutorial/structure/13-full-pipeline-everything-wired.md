# Session 13: Full Pipeline — Everything Wired

## Goal
Wire all components together: world engine → sensors → queue → cluster agents → supervisor → commands. One complete simulation run with all systems active.

## Rubric Skills Introduced
| Skill | Level | Section |
|-------|-------|---------|
| LangSmith tracing | mid-level | 7. Streaming and Observability |

## Key Concepts
- **Pipeline stages** — engine, sensors, publisher, queue, consumer, cluster agents, supervisor, actuator commands
- **Resource integration** — supervisor queries preparedness during assessment
- **Ground truth snapshots** — engine.history captures what actually happened
- **LangSmith** — traces the full execution for debugging

## What You Build
1. Create engine + resources from scenario
2. Set up sensors + publisher + queue
3. Set up consumer with cluster agent graph
4. Set up supervisor with resource awareness
5. Run full pipeline: publish → consume → supervise
6. Inspect results: findings, commands, snapshots

## What You Can Run
```python
import asyncio
import random
from domains.wildfire import create_full_wildfire_scenario
from domains.wildfire.sensors import TemperatureSensor, SmokeSensor
from sensors import SensorPublisher
from transport import SensorEventQueue
from bridge.consumer import EventBridgeConsumer
from agents.cluster.graph import build_cluster_agent_graph
from agents.supervisor.graph import build_supervisor_graph

async def main():
    random.seed(42)
    engine, resources = create_full_wildfire_scenario()

    queue = SensorEventQueue()
    sensors = [
        TemperatureSensor(source_id="temp-n1", cluster_id="cluster-north",
                          engine=engine, grid_row=3, grid_col=3),
        SmokeSensor(source_id="smoke-s1", cluster_id="cluster-south",
                    engine=engine, grid_row=7, grid_col=5),
    ]

    publisher = SensorPublisher(sensors=sensors, queue=queue, engine=engine)
    cluster_graph = build_cluster_agent_graph()

    findings = []
    consumer = EventBridgeConsumer(
        queue=queue, agent_graph=cluster_graph, batch_size=5,
        on_finding=lambda f: findings.append(f),
    )

    # Run sensor pipeline
    await publisher.run(ticks=20)
    await consumer.run(max_events=queue.total_enqueued)

    # Run supervisor
    supervisor_graph = build_supervisor_graph()
    result = supervisor_graph.invoke({
        "active_cluster_ids": ["cluster-north", "cluster-south"],
        "cluster_findings": findings,
        "messages": [],
        "pending_commands": [],
        "situation_summary": None,
        "status": "idle",
    })

    # Results
    print(f"Events: {consumer.events_consumed}")
    print(f"Findings: {len(findings)}")
    print(f"Summary: {result['situation_summary']}")
    print(f"Commands: {len(result['pending_commands'])}")
    print(f"\nResource readiness:")
    for rtype, info in resources.readiness_summary()["by_type"].items():
        print(f"  {rtype}: {info['available']}/{info['total']} available")

asyncio.run(main())
```

## Key Files
- `examples/pipeline_demo_annotated.py` — complete reference implementation

## Verification
- All stages complete without errors
- Findings are produced from real sensor events
- Supervisor produces a situation summary
- Resource readiness is available for comparison
- Ground truth in engine.history matches fire spread

## Next Session
Session 14 uses scenario knobs to test agent resilience under degraded conditions.
