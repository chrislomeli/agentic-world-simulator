#!/usr/bin/env python3
"""Runnable version of notebooks/pipeline_demo.ipynb."""

import asyncio
import logging
import os
import random

import langsmith
from langgraph.store.memory import InMemoryStore

from ogar.agents.cluster.graph import build_cluster_agent_graph
from ogar.agents.supervisor.graph import build_supervisor_graph
from ogar.bridge.consumer import EventBridgeConsumer
from ogar.config import get_settings
from ogar.domains.wildfire.scenarios import create_basic_wildfire
from ogar.domains.wildfire.sensors import (
    HumiditySensor,
    SmokeSensor,
    TemperatureSensor,
    WindSensor,
)
from ogar.sensors.publisher import SensorPublisher
from ogar.transport.queue import SensorEventQueue
from ogar.world.grid import FireState, TerrainType


def configure_environment():
    os.environ.setdefault("AI_ENV_FILE", "/Users/chrislomeli/Source/SECRETS/.env")
    settings = get_settings()
    settings.apply_langsmith()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-35s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    print(f"LangSmith tracing: {settings.langchain_tracing_v2}")
    print(f"LangSmith project: {settings.langchain_project}")
    print(f"Anthropic key set: {bool(settings.anthropic_api_key)}")
    return settings


def choose_llm(settings):
    llm = None

    # from langchain_anthropic import ChatAnthropic
    # llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0,
    #                     api_key=settings.anthropic_api_key)

    # from langchain_openai import ChatOpenAI
    # llm = ChatOpenAI(model="gpt-4o-mini", temperature=0,
    #                  api_key=settings.openai_api_key)

    mode = "LLM" if llm else "STUB"
    print(f"Running in {mode} mode")
    return llm, mode


def render_grid(engine, sensor_positions=None):
    terrain = {
        TerrainType.FOREST: "T",
        TerrainType.GRASSLAND: ".",
        TerrainType.ROCK: "#",
        TerrainType.WATER: "~",
        TerrainType.SCRUB: "s",
        TerrainType.URBAN: "U",
    }
    sensor_positions = sensor_positions or set()

    rows = []
    for row_idx in range(engine.grid.rows):
        row = []
        for col_idx in range(engine.grid.cols):
            cell = engine.grid.get_cell(row_idx, col_idx)
            state = cell.cell_state
            if state.fire_state == FireState.BURNING:
                glyph = "F"
            elif state.fire_state == FireState.BURNED:
                glyph = "*"
            elif (row_idx, col_idx) in sensor_positions:
                glyph = "S"
            else:
                glyph = terrain.get(state.terrain_type, "?")
            row.append(glyph)
        rows.append(" ".join(row))

    print("  " + " ".join(str(col) for col in range(engine.grid.cols)))
    for idx, row in enumerate(rows):
        print(f"{idx} {row}")
    print()
    print("Legend: T=Forest  .=Grass  #=Rock  ~=Water  s=Scrub  U=Urban  F=Burning  *=Burned  S=Sensor")


async def main():
    settings = configure_environment()
    llm, mode = choose_llm(settings)

    random.seed(42)
    engine = create_basic_wildfire()

    print(f"Grid: {engine.grid.rows}×{engine.grid.cols}")
    print(
        f"Weather: {engine.environment.temperature_c}°C, "
        f"{engine.environment.humidity_pct}% humidity, "
        f"{engine.environment.wind_speed_mps} m/s wind"
    )
    print(f"Fire state: {engine.grid.summary_counts()}")
    print("--- Initial world state ---")
    render_grid(engine)

    sensors = [
        TemperatureSensor(source_id="temp-N1", cluster_id="cluster-north", engine=engine, grid_row=2, grid_col=3, noise_std=0.5),
        TemperatureSensor(source_id="temp-N2", cluster_id="cluster-north", engine=engine, grid_row=3, grid_col=6, noise_std=0.5),
        SmokeSensor(source_id="smoke-N1", cluster_id="cluster-north", engine=engine, grid_row=3, grid_col=4, noise_std=1.0),
        HumiditySensor(source_id="hum-N1", cluster_id="cluster-north", engine=engine, noise_std=0.5),
        WindSensor(source_id="wind-N1", cluster_id="cluster-north", engine=engine),
        TemperatureSensor(source_id="temp-S1", cluster_id="cluster-south", engine=engine, grid_row=6, grid_col=2, noise_std=0.5),
        TemperatureSensor(source_id="temp-S2", cluster_id="cluster-south", engine=engine, grid_row=7, grid_col=4, noise_std=0.5),
        SmokeSensor(source_id="smoke-S1", cluster_id="cluster-south", engine=engine, grid_row=7, grid_col=3, noise_std=1.0),
        HumiditySensor(source_id="hum-S1", cluster_id="cluster-south", engine=engine, noise_std=0.5),
        WindSensor(source_id="wind-S1", cluster_id="cluster-south", engine=engine),
    ]

    sensor_positions = {(2, 3), (3, 6), (3, 4), (6, 2), (7, 4), (7, 3)}
    print(f"Created {len(sensors)} sensors across 2 clusters:")
    for sensor in sensors:
        print(f"  {sensor.source_id:12s}  cluster={sensor.cluster_id}")
    print()
    print("--- World with sensor positions ---")
    render_grid(engine, sensor_positions)

    sample_event = sensors[5].emit()
    print("Raw SensorEvent:")
    print(f"  event_id:    {sample_event.event_id}")
    print(f"  source_id:   {sample_event.source_id}")
    print(f"  source_type: {sample_event.source_type}")
    print(f"  cluster_id:  {sample_event.cluster_id}")
    print(f"  sim_tick:    {sample_event.sim_tick}")
    print(f"  confidence:  {sample_event.confidence}")
    print(f"  payload:     {sample_event.payload}")

    queue = SensorEventQueue(maxsize=500)
    publisher = SensorPublisher(
        sensors=sensors,
        queue=queue,
        tick_interval_seconds=0.0,
        engine=engine,
    )
    print("Queue and publisher ready")

    store = InMemoryStore()
    cluster_graph = build_cluster_agent_graph(llm=llm, store=store)
    supervisor_graph = build_supervisor_graph(llm=llm, store=store)
    print(f"Cluster agent:    {mode} mode  (store: {type(store).__name__})")
    print(f"Supervisor agent: {mode} mode  (store: {type(store).__name__})")

    findings_log = []

    def on_finding(finding):
        findings_log.append(finding)
        confidence = finding["confidence"]
        bar = "=" * int(confidence * 20)
        print(
            f"  [{finding['cluster_id']:15s}] [{bar:<20s}] {confidence:.0%}  "
            f"{finding['anomaly_type']}: {finding['summary'][:60]}"
        )

    consumer = EventBridgeConsumer(
        queue=queue,
        agent_graph=cluster_graph,
        on_finding=on_finding,
        batch_size=5,
    )
    print("Consumer ready (batch_size=5)")

    num_ticks = 20
    print("=" * 65)
    print(f"Pipeline starting: {num_ticks} world ticks")
    print("=" * 65)
    print()
    print("Cluster findings as they arrive:")
    print(f"  {'cluster':17s} {'confidence':22s} anomaly: summary")
    print("  " + "-" * 62)

    with langsmith.trace(
        name="ogar-pipeline",
        run_type="chain",
        metadata={"num_ticks": num_ticks, "mode": mode, "clusters": ["cluster-north", "cluster-south"]},
    ):
        await publisher.run(ticks=num_ticks)
        await consumer.run(max_events=queue.total_enqueued)

    print()
    print("=" * 65)
    print("Pipeline complete")
    print(f"  World ticks:      {engine.current_tick}")
    print(f"  Events produced:  {queue.total_enqueued}")
    print(f"  Events consumed:  {consumer.events_consumed}")
    print(f"  Agent invocations:{consumer.invocations}")
    print(f"  Findings:         {len(findings_log)}")
    print("=" * 65)

    burning = [
        (row, col)
        for row in range(engine.grid.rows)
        for col in range(engine.grid.cols)
        if engine.grid.get_cell(row, col).cell_state.fire_state == FireState.BURNING
    ]
    burned = [
        (row, col)
        for row in range(engine.grid.rows)
        for col in range(engine.grid.cols)
        if engine.grid.get_cell(row, col).cell_state.fire_state == FireState.BURNED
    ]

    print("GROUND TRUTH (world engine — agents never see this)")
    print(f"  Currently burning: {len(burning)} cells  {burning}")
    print(f"  Burned out:        {len(burned)} cells")
    print(f"  Total affected:    {len(burning) + len(burned)} cells")
    print()

    print("--- World state after pipeline ---")
    render_grid(engine, sensor_positions)

    print("AGENT FINDINGS")
    if not findings_log:
        print("  No anomalies detected.")
    else:
        for finding in findings_log:
            print(f"  [{finding['cluster_id']:15s}] {finding['anomaly_type']:20s} conf={finding['confidence']:.2f}")
            print(f"    {finding['summary']}")
            print(f"    Sensors: {finding['affected_sensors']}")

    print()
    print("CROSS-AGENT STORE CONTENTS")
    for cluster_id in ["cluster-north", "cluster-south"]:
        items = store.search(("incidents", cluster_id))
        print(f"  ('incidents', '{cluster_id}')  →  {len(items)} item(s)")
        for item in items:
            value = item.value
            print(
                f"    [{item.key[:8]}]  {value.get('anomaly_type'):20s}  "
                f"conf={value.get('confidence', 0):.2f}  {value.get('summary', '')[:50]}"
            )

    with langsmith.trace(
        name="ogar-supervisor",
        run_type="chain",
        metadata={"mode": mode, "findings_count": len(findings_log)},
    ):
        supervisor_result = supervisor_graph.invoke(
            {
                "active_cluster_ids": ["cluster-north", "cluster-south"],
                "cluster_findings": findings_log,
                "messages": [],
                "pending_commands": [],
                "situation_summary": None,
                "status": "idle",
            },
            config={"run_name": "supervisor-assess-decide"},
        )

    print("SUPERVISOR RESULT")
    print(f"  Status:   {supervisor_result['status']}")
    print(f"  Summary:  {supervisor_result.get('situation_summary', 'none')}")
    print()

    commands = supervisor_result.get("pending_commands", [])
    print(f"  Commands issued: {len(commands)}")
    for cmd in commands:
        print(f"    [{cmd.priority}] {cmd.command_type:12s} cluster={cmd.cluster_id}")
        print(f"         payload: {cmd.payload}")


if __name__ == "__main__":
    asyncio.run(main())
