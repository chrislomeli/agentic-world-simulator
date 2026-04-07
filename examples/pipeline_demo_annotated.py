#!/usr/bin/env python3
"""
pipeline_demo.py — ANNOTATED FOR LEARNING

This script demonstrates the complete agent-driven simulation pipeline:

    World Engine (wildfire)
           ↓
    Sensors (emit readings)
           ↓
    Event Queue (collects readings)
           ↓
    Cluster Agents (analyze by region)
           ↓
    Findings (anomalies detected)
           ↓
    Supervisor Agent (coordinates response)

The flow is: world → sensors → queue → cluster agents → supervisor

Let's trace each step!
"""

import asyncio
import logging
import os
import random

import langsmith
from langgraph.store.memory import InMemoryStore

from agents.cluster.graph import build_cluster_agent_graph
from agents.supervisor.graph import build_supervisor_graph
from bridge.consumer import EventBridgeConsumer
from config import get_settings
from domains.wildfire.scenarios import create_basic_wildfire
from domains.wildfire.sensors import (
    HumiditySensor,
    SmokeSensor,
    TemperatureSensor,
    WindSensor,
)
from sensors import SensorPublisher
from transport import SensorEventQueue
from world.grid import FireState, TerrainType
from world.sensor_inventory import SensorInventory


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: SETUP & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

def configure_environment():
    """
    Load API keys, configure logging, set up LangSmith tracing.

    Think of this as: "open the door, turn on the lights, get your tools ready"
    """
    os.environ.setdefault("AI_ENV_FILE", "/Users/chrislomeli/Source/SECRETS/.env")
    settings = get_settings()  # Load .env file (API keys, project names, etc.)
    settings.apply_langsmith()  # Enable LangSmith tracing for debugging agent calls

    # Set up Python logging so we can see what's happening
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-35s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy HTTP logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Print what we're using
    print(f"LangSmith tracing: {settings.langchain_tracing_v2}")
    print(f"LangSmith project: {settings.langchain_project}")
    print(f"Anthropic key set: {bool(settings.anthropic_api_key)}")
    return settings


def choose_llm(settings):
    """
    Choose which LLM to use (or run in STUB mode with no LLM).

    The code is set up to use either Claude, GPT-4, or a stub (deterministic fake).
    For learning, STUB mode is fine. To use a real LLM, uncomment one of the options.

    Returns:
        (llm_object, "LLM" or "STUB") — the LLM callable and which mode we're running
    """
    llm = None

    # Option 1: Use Claude (requires ANTHROPIC_API_KEY)
    # from langchain_anthropic import ChatAnthropic
    # llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0,
    #                     api_key=settings.anthropic_api_key)

    # Option 2: Use GPT-4 (requires OPENAI_API_KEY)
    # from langchain_openai import ChatOpenAI
    # llm = ChatOpenAI(model="gpt-4o-mini", temperature=0,
    #                  api_key=settings.openai_api_key)

    mode = "LLM" if llm else "STUB"  # If llm is None, we'll use deterministic responses
    print(f"Running in {mode} mode")
    return llm, mode


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: WORLD VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def render_grid(engine, inventory=None, layers=None):
    """
    Draw the world as ASCII art so we can see what's happening.

    Example output:
        0 T T T T T T T T T T
        1 T T T T T T T T T T
        2 T T t T T T T T T T    <- t is a temperature sensor
        3 T T T k T T T T T T    <- k is a smoke sensor
        ...

    Parameters:
        engine    : the world engine (provides grid state)
        inventory : optional SensorInventory — positions derived automatically
        layers    : optional list of source_type strings to show (e.g. ["smoke"]).
                    If None, all sensor types are shown.

    Legend:
        T = Forest (burns easily)
        . = Grassland
        # = Rock (won't burn)
        ~ = Water (won't burn)
        s = Scrub
        U = Urban
        F = Currently burning
        * = Already burned
        Sensor glyphs: t=temperature  k=smoke  h=humidity  w=wind  b=barometric  c=camera  +=overlap
    """
    # Glyph mapping: terrain type → character
    terrain = {
        TerrainType.FOREST: "T",
        TerrainType.GRASSLAND: ".",
        TerrainType.ROCK: "#",
        TerrainType.WATER: "~",
        TerrainType.SCRUB: "s",
        TerrainType.URBAN: "U",
    }

    # Sensor type → glyph
    sensor_glyph = {
        "temperature": "t",
        "smoke": "k",
        "humidity": "h",
        "wind": "w",
        "barometric_pressure": "b",
        "thermal_camera": "c",
    }

    # Build a position → glyph map from the inventory
    sensor_positions = {}  # (row, col) → glyph
    if inventory is not None:
        show_types = set(layers) if layers else inventory.layer_types()
        for stype in show_types:
            for pos in inventory.layer_positions(stype):
                rc = (pos[0], pos[1])  # project to 2D for rendering
                if rc in sensor_positions:
                    sensor_positions[rc] = "+"  # overlap
                else:
                    sensor_positions[rc] = sensor_glyph.get(stype, "?")

    rows = []
    # For each row in the grid
    for row_idx in range(engine.grid.rows):
        row = []
        # For each column in the grid
        for col_idx in range(engine.grid.cols):
            cell = engine.grid.get_cell(row_idx, col_idx)
            state = cell.cell_state

            # Decide what character to draw
            if state.fire_state == FireState.BURNING:
                glyph = "F"  # On fire now
            elif state.fire_state == FireState.BURNED:
                glyph = "*"  # Already burned
            elif (row_idx, col_idx) in sensor_positions:
                glyph = sensor_positions[(row_idx, col_idx)]
            else:
                glyph = terrain.get(state.terrain_type, "?")  # Terrain type

            row.append(glyph)

        rows.append(" ".join(row))

    # Print with column numbers on top
    print("  " + " ".join(str(col) for col in range(engine.grid.cols)))
    for idx, row in enumerate(rows):
        print(f"{idx} {row}")
    print()
    print("Legend: T=Forest  .=Grass  #=Rock  ~=Water  s=Scrub  U=Urban  F=Burning  *=Burned")
    print("Sensors: t=temp  k=smoke  h=humidity  w=wind  b=barometric  c=camera  +=overlap")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    """
    The main pipeline orchestrator.

    Flow:
    1. Set up the world (wildfire engine on a grid)
    2. Place sensors in the world
    3. Run the event loop: sensors emit → agents process → supervisor decides
    4. Print results
    """

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 1: INITIALIZE
    # ───────────────────────────────────────────────────────────────────────────

    settings = configure_environment()
    llm, mode = choose_llm(settings)

    # Set random seed for reproducibility (so the fire always starts in the same place)
    random.seed(42)

    # Create the world — a grid with terrain, weather, and fire dynamics
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

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 2: CREATE SENSORS
    # ───────────────────────────────────────────────────────────────────────────

    # We'll have 2 clusters of sensors: north and south regions of the world
    sensors = [
        # NORTH cluster sensors
        TemperatureSensor(source_id="temp-N1", cluster_id="cluster-north", engine=engine, grid_row=2, grid_col=3, noise_std=0.5),
        TemperatureSensor(source_id="temp-N2", cluster_id="cluster-north", engine=engine, grid_row=3, grid_col=6, noise_std=0.5),
        SmokeSensor(source_id="smoke-N1", cluster_id="cluster-north", engine=engine, grid_row=3, grid_col=4, noise_std=1.0),
        HumiditySensor(source_id="hum-N1", cluster_id="cluster-north", engine=engine, grid_row=2, grid_col=4, noise_std=0.5),
        WindSensor(source_id="wind-N1", cluster_id="cluster-north", engine=engine, grid_row=2, grid_col=5),

        # SOUTH cluster sensors
        TemperatureSensor(source_id="temp-S1", cluster_id="cluster-south", engine=engine, grid_row=6, grid_col=2, noise_std=0.5),
        TemperatureSensor(source_id="temp-S2", cluster_id="cluster-south", engine=engine, grid_row=7, grid_col=4, noise_std=0.5),
        SmokeSensor(source_id="smoke-S1", cluster_id="cluster-south", engine=engine, grid_row=7, grid_col=3, noise_std=1.0),
        HumiditySensor(source_id="hum-S1", cluster_id="cluster-south", engine=engine, grid_row=6, grid_col=3, noise_std=0.5),
        WindSensor(source_id="wind-S1", cluster_id="cluster-south", engine=engine, grid_row=6, grid_col=4),
    ]

    # Register all sensors in the inventory — positions come from the sensors themselves
    inventory = SensorInventory(
        grid_rows=engine.grid.rows,
        grid_cols=engine.grid.cols,
    )
    for sensor in sensors:
        inventory.register_auto(sensor)

    print(f"Created {len(sensors)} sensors across 2 clusters:")
    for sensor in sensors:
        print(f"  {sensor.source_id:12s}  cluster={sensor.cluster_id}  at ({sensor.grid_row}, {sensor.grid_col})")
    print(f"Sensor layers: {inventory.layer_types()}")
    print()
    print("--- World with sensor positions ---")
    render_grid(engine, inventory=inventory)

    # Show what a sensor event looks like
    sample_event = sensors[5].emit()
    print("Raw SensorEvent:")
    print(f"  event_id:    {sample_event.event_id}")
    print(f"  source_id:   {sample_event.source_id}")
    print(f"  source_type: {sample_event.source_type}")
    print(f"  cluster_id:  {sample_event.cluster_id}")
    print(f"  sim_tick:    {sample_event.sim_tick}")
    print(f"  confidence:  {sample_event.confidence}")
    print(f"  payload:     {sample_event.payload}")

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 3: SET UP THE EVENT PIPELINE
    # ───────────────────────────────────────────────────────────────────────────

    # Queue: where sensor readings accumulate
    queue = SensorEventQueue(maxsize=500)

    # Publisher: loops through sensors, calls .emit() on each, puts event in queue
    publisher = SensorPublisher(
        inventory=inventory,
        queue=queue,
        tick_interval_seconds=0.0,  # No delay between ticks (go fast)
        engine=engine,
    )
    print("Queue and publisher ready")

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 4: BUILD THE AGENT GRAPHS
    # ───────────────────────────────────────────────────────────────────────────

    # Shared memory store: agents can write findings here that other agents can read
    # (InMemoryStore = data lost when process ends, but fine for demos)
    store = InMemoryStore()

    # Two types of agents:
    # 1. Cluster agents — analyze sensor events from their region
    # 2. Supervisor agent — looks at all findings, makes decisions
    cluster_graph = build_cluster_agent_graph(llm=llm, store=store)
    supervisor_graph = build_supervisor_graph(llm=llm, store=store)
    print(f"Cluster agent:    {mode} mode  (store: {type(store).__name__})")
    print(f"Supervisor agent: {mode} mode  (store: {type(store).__name__})")

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 5: SET UP THE CONSUMER (processes queue with agents)
    # ───────────────────────────────────────────────────────────────────────────

    findings_log = []

    # Callback: when an agent detects an anomaly (fire), this function is called
    def on_finding(finding):
        findings_log.append(finding)
        confidence = finding["confidence"]
        bar = "=" * int(confidence * 20)  # Visual confidence bar
        print(
            f"  [{finding['cluster_id']:15s}] [{bar:<20s}] {confidence:.0%}  "
            f"{finding['anomaly_type']}: {finding['summary'][:60]}"
        )

    # Consumer: reads from queue, batches events, sends to cluster agent
    consumer = EventBridgeConsumer(
        queue=queue,
        agent_graph=cluster_graph,
        on_finding=on_finding,
        batch_size=5,  # Process 5 events at a time
    )
    print("Consumer ready (batch_size=5)")

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 6: RUN THE MAIN LOOP
    # ───────────────────────────────────────────────────────────────────────────

    num_ticks = 20
    print("=" * 65)
    print(f"Pipeline starting: {num_ticks} world ticks")
    print("=" * 65)
    print()
    print("Cluster findings as they arrive:")
    print(f"  {'cluster':17s} {'confidence':22s} anomaly: summary")
    print("  " + "-" * 62)

    # Wrap everything in LangSmith tracing so we can debug later
    with langsmith.trace(
        name="ogar-pipeline",
        run_type="chain",
        metadata={"num_ticks": num_ticks, "mode": mode, "clusters": ["cluster-north", "cluster-south"]},
    ):
        # Run the world for N ticks (each tick = 1 world simulation step)
        await publisher.run(ticks=num_ticks)

        # Process all the events that were emitted
        await consumer.run(max_events=queue.total_enqueued)

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 7: PRINT RESULTS
    # ───────────────────────────────────────────────────────────────────────────

    print()
    print("=" * 65)
    print("Pipeline complete")
    print(f"  World ticks:      {engine.current_tick}")
    print(f"  Events produced:  {queue.total_enqueued}")
    print(f"  Events consumed:  {consumer.events_consumed}")
    print(f"  Agent invocations:{consumer.invocations}")
    print(f"  Findings:         {len(findings_log)}")
    print("=" * 65)

    # What actually happened in the world (ground truth)
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
    render_grid(engine, inventory=inventory)

    # What the agents detected
    print("AGENT FINDINGS")
    if not findings_log:
        print("  No anomalies detected.")
    else:
        for finding in findings_log:
            print(f"  [{finding['cluster_id']:15s}] {finding['anomaly_type']:20s} conf={finding['confidence']:.2f}")
            print(f"    {finding['summary']}")
            print(f"    Sensors: {finding['affected_sensors']}")

    # Data shared between agents (stored in the InMemoryStore)
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

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 8: RUN THE SUPERVISOR AGENT
    # ───────────────────────────────────────────────────────────────────────────

    # Now the supervisor looks at all findings and decides what to do
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


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # asyncio.run() starts the async event loop and runs main()
    # (More on async/await in a moment if you need it!)
    asyncio.run(main())
