#!/usr/bin/env python3
"""
pipeline_demo.py — ANNOTATED FOR LEARNING

This script demonstrates the complete agent-driven simulation pipeline:

    World Engine (wildfire)
           ↓
    Sampler (samples local conditions at sensor positions)
           ↓
    Sensors (add noise to local conditions → readings)
           ↓
    Publisher → Event Queue (collects readings)
           ↓
    Consumer (groups events by cluster)
           ↓
    Supervisor Agent (fans out to cluster agents, correlates, decides)

The flow is: world → sampler → sensors → queue → consumer → supervisor → cluster agents → commands

Let's trace each step!
"""

import asyncio

from examples.config_builder import configure_environment
from examples.pipeline_builder import build_pipeline
from examples.supervisor_runner import run_with_supervisor
from langgraph.store.memory import InMemoryStore

from agents.supervisor.graph import build_supervisor_graph
from domains.wildfire.scenario_loader import load_scenario_from_json
from world.grid import FireState, TerrainType


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: SETUP & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
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


    # ───────────────────────────────────────────────────────────────────────────
    # STEP 00: INITIALIZE
    # ───────────────────────────────────────────────────────────────────────────
    settings = configure_environment()

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 01: CREATE WORLD
    # ───────────────────────────────────────────────────────────────────────────
    engine, sensor_inventory, resource_inventory = load_scenario_from_json(settings.world_data)

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 02: cluster agent with Stub
    # STEP 03: cluster agent with LLM
    # ───────────────────────────────────────────────────────────────────────────
    llm, mode = choose_llm(settings)  # todo change this

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 04: Build the pipeline (pub/sub)
    # ───────────────────────────────────────────────────────────────────────────
    #
    # The pipeline is self-contained: publisher + consumer running concurrently.
    # It knows nothing about agents or supervisors.  You can test it standalone
    # with:  events = await pipeline.run_to_completion(num_ticks=20)
    pipeline = build_pipeline(engine, sensor_inventory)


    # ───────────────────────────────────────────────────────────────────────────
    # STEP 05: Build the supervisor graph and wire it to the pipeline
    # ───────────────────────────────────────────────────────────────────────────
    #
    # One graph invocation does everything:
    #   supervisor_graph.invoke({events_by_cluster: ...})
    #     → fan_out_to_clusters (Send API) → cluster agents in parallel
    #     → [synchronization barrier]
    #     → assess_situation → decide_actions → dispatch_commands

    store = InMemoryStore()
    supervisor_graph = build_supervisor_graph(llm=llm, store=store)
    print(f"Supervisor graph: {mode} mode  (store: {type(store).__name__})")

    num_ticks = 20
    supervisor_interval = 10

    supervisor_results = await run_with_supervisor(
        pipeline=pipeline,
        supervisor_graph=supervisor_graph,
        num_ticks=num_ticks,
        supervisor_interval=supervisor_interval,
        mode=mode,
    )

    # Use the last supervisor result for the summary below
    supervisor_result = supervisor_results[-1][1] if supervisor_results else {}

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 6: PRINT RESULTS
    # ───────────────────────────────────────────────────────────────────────────

    print()
    print("=" * 65)
    print("Pipeline complete")
    print(f"  World ticks:        {engine.current_tick}")
    print(f"  Supervisor calls:   {len(supervisor_results)}")
    print(f"  Invocation ticks:   {[t for t, _ in supervisor_results]}")
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
    render_grid(engine, inventory=sensor_inventory)

    # What the agents detected (findings produced by supervisor's cluster agent fan-out)
    findings = supervisor_result.get("cluster_findings", [])
    print("AGENT FINDINGS")
    if not findings:
        print("  No anomalies detected.")
    else:
        for finding in findings:
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

    # Supervisor result
    print()
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
    asyncio.run(main())
