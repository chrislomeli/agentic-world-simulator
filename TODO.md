# OGAR — Project Backlog

OGAR is a domain-agnostic event-driven agent testbed built on LangGraph + Kafka + K8s.
The wildfire scenario is the reference domain skin.

---

## In Progress

| # | Area | Description |
|---|------|-------------|
| — | Sensor periodicity | Add `emit_every_n_ticks` to `SensorBase`; publisher skips emit when world tick doesn't align |

---

## Backlog

| #  | Area                     | Description                                                                                                         | Priority |
|----|--------------------------|---------------------------------------------------------------------------------------------------------------------|----------|
| 1  | Second domain            | Build a second domain (ocean currents, disease spread, etc.) to validate the generic framework actually generalizes | High |
| 2  | Sensor periodicity       | Per-sensor emit rate tied to world tick — no sensor emits faster than one world tick                                | High |
| 3  | Scenario scripts         | Time-varying experiments: inject sensor failures, change environment conditions, thin inventory mid-run             | Medium |
| 4  | LangSmith tracing        | Wire `LANGCHAIN_TRACING_V2` into agent entry points for observability                                               | Medium |
| 5  | Notebook update          | Update `notebooks/pipeline_demo.ipynb` to use new generic engine + wildfire domain APIs                             | Medium |
| 6  | Kafka swap               | Replace `SensorEventQueue` (asyncio) with a real Kafka producer/consumer                                            | Medium |
| 7  | K8s deploy               | Helm chart / manifests to run the pipeline in a local k3s cluster                                                   | Low |
| 8  | Temporal swap            | Replace `WorkflowStub` (asyncio Tasks) with real Temporal workers                                                   | Low |
| 9  | Actuator implementations | Concrete actuators: Slack notify, PagerDuty alert, drone task dispatcher                                            | Low |
| 10 | Evaluation harness       | Ground truth vs agent findings scoring — precision/recall per scenario                                              | Low |
| 11 | Named Cells              | Currenly, all cells are GenericCells - I think it's becuase we are using ABC                                        | Low |
---

## Completed

| Area | Description |
|------|-------------|
| Generic framework | `GenericWorldEngine[C]`, `GenericTerrainGrid[C]`, `PhysicsModule`, `EnvironmentState`, `CellState`, `StateEvent`, `SensorInventory` |
| Wildfire domain | `FireCellState`, `FireEnvironmentState`, `FirePhysicsModule`, all 6 sensors, `create_basic_wildfire()` |
| Phase 4 cleanup | Deleted old `fire_spread/`, `engine.py`, `scenarios/`, `world_sensors.py`; updated all tests and tutorials to new API |
| Cluster agent | LangGraph graph, stub + LLM mode, ToolNode loop, 4 sensor tools |
| Supervisor agent | LangGraph graph, stub + LLM mode, Send API fan-out, assess/decide/dispatch loop |
| Transport | `SensorEvent` schema, asyncio queue, topic definitions |
| Bridge consumer | Async event routing, cluster→graph dispatch |
| Tutorials | 4-part tutorial series updated to new generic API |

---

## Known test gaps

- `tests/transport/test_queue.py` — collection error (pre-existing)
- `tests/workflow/test_runner.py` — ~7 failures (pytest-asyncio config mismatch, pre-existing)
- `tests/test_config.py` — one test picks up real API key from env (pre-existing)
