#!/usr/bin/env python3
"""
pipeline_demo.py — ANNOTATED FOR LEARNING

This script demonstrates the complete pipeline from world engine to
supervisor graph, with clean separation of concerns:

    Pipeline (data ingestion)
        WorldEngine → Sensors → Publisher → Queue → Consumer → LocationStateStore

    Event Loop (decision layer)
        LocationStateStore → ScoringFilter → on_batch → Supervisor Graph

    Supervisor Graph (agent orchestration)
        fan_out_to_clusters (Send API) → cluster agents in parallel
        → [synchronization barrier]
        → assess_situation → decide_actions → dispatch_commands

The LocationStateStore is the seam between the pipeline and the event
loop.  The pipeline writes aggregated sensor data into the store.
The event loop reads from the store, decides what's interesting, and
invokes the supervisor.

Neither side knows about the other — the store is the contract.
"""

import asyncio

from examples.config_builder import configure_environment
from examples.event_loop_builder import (
    build_event_loop,
    make_supervisor_callback,
    run_pipeline_with_event_loop,
)
from examples.pipeline_builder import build_pipeline
from langgraph.store.memory import InMemoryStore

from agents.supervisor.graph import build_supervisor_graph
from domains.wildfire.scenario_loader import load_scenario_from_json
from event_loop.sensor_filter import score_location
from event_loop.store import InMemoryLocationStore
from resources import evaluate_preparedness, severity_from_score
from resources.inventory import ResourceInventory
from world.grid import FireState, TerrainType

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: SETUP & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

def choose_llm(settings):
    """
    Choose which LLM to use (or run in STUB mode with no LLM).

    For learning, STUB mode is fine. To use a real LLM, uncomment one option.
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

    mode = "LLM" if llm else "STUB"
    print(f"Running in {mode} mode")
    return llm, mode


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: WORLD VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def render_grid(engine, inventory=None, layers=None):
    """
    Draw the world as ASCII art so we can see what's happening.

    Legend:
        T = Forest  . = Grass  # = Rock  ~ = Water  s = Scrub  U = Urban
        F = Burning  * = Burned
        Sensors: t=temp  k=smoke  h=humidity  w=wind  b=barometric  c=camera  +=overlap
    """
    terrain = {
        TerrainType.FOREST: "T", TerrainType.GRASSLAND: ".",
        TerrainType.ROCK: "#", TerrainType.WATER: "~",
        TerrainType.SCRUB: "s", TerrainType.URBAN: "U",
    }
    sensor_glyph = {
        "temperature": "t", "smoke": "k", "humidity": "h",
        "wind": "w", "barometric_pressure": "b", "thermal_camera": "c",
    }

    sensor_positions = {}
    if inventory is not None:
        show_types = set(layers) if layers else inventory.layer_types()
        for stype in show_types:
            for pos in inventory.layer_positions(stype):
                rc = (pos[0], pos[1])
                if rc in sensor_positions:
                    sensor_positions[rc] = "+"
                else:
                    sensor_positions[rc] = sensor_glyph.get(stype, "?")

    print("  " + " ".join(str(col) for col in range(engine.grid.cols)))
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
                glyph = sensor_positions[(row_idx, col_idx)]
            else:
                glyph = terrain.get(state.terrain_type, "?")
            row.append(glyph)
        print(f"{row_idx} {' '.join(row)}")
    print()
    print("Legend: T=Forest  .=Grass  #=Rock  ~=Water  s=Scrub  U=Urban  F=Burning  *=Burned")
    print("Sensors: t=temp  k=smoke  h=humidity  w=wind  b=barometric  c=camera  +=overlap")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: PREPAREDNESS REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def print_preparedness_report(
    location_store: InMemoryLocationStore,
    resource_inventory: ResourceInventory,
):
    """
    After the pipeline runs, evaluate preparedness for each location
    that has sensor data in the store.

    This shows the full chain:
        sensor score → severity → SLA check → posture
    """
    print()
    print("PREPAREDNESS EVALUATION")
    print("-" * 65)
    for location_id in location_store.get_all_location_ids():
        state = location_store.get(location_id)
        if not state:
            continue

        result = score_location(state)
        severity = severity_from_score(result.total_score, result.threshold)
        prep = evaluate_preparedness(
            severity, location_id, resource_inventory,
        )
        print(f"  {prep.summary}")
        if prep.gaps:
            for gap in prep.gaps:
                print(f"    - {gap.reason}")
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

async def main():

    # ── STEP 1: Load scenario ─────────────────────────────────────────────────
    settings = configure_environment()
    engine, sensor_inventory, resource_inventory = load_scenario_from_json(settings.world_data)

    # ── STEP 2: Choose LLM or STUB ───────────────────────────────────────────
    llm, mode = choose_llm(settings)

    # ── STEP 3: Build the shared LocationStateStore ──────────────────────────
    #
    # This is the seam between the pipeline and the event loop.
    # The pipeline's consumer writes here.  The event loop reads here.
    location_store = InMemoryLocationStore()

    # ── STEP 4: Build the data pipeline ──────────────────────────────────────
    #
    # WorldEngine → Sensors → Publisher → Queue → Consumer → LocationStateStore
    #
    # The pipeline is LangGraph-free.  It knows nothing about agents.
    pipeline = build_pipeline(engine, sensor_inventory, store=location_store)

    # ── STEP 5: Build the supervisor graph ───────────────────────────────────
    #
    # One graph invocation handles everything:
    #   fan_out_to_clusters (Send API) → cluster agents in parallel
    #   → [synchronization barrier]
    #   → assess_situation → decide_actions → dispatch_commands
    agent_store = InMemoryStore()
    supervisor_graph = build_supervisor_graph(llm=llm, store=agent_store)
    print(f"Supervisor graph: {mode} mode  (store: {type(agent_store).__name__})")

    # ── STEP 6: Build the event loop ─────────────────────────────────────────
    #
    # LocationStateStore → ScoringFilter → on_batch → supervisor_graph.invoke()
    #
    # The event loop polls the store, checks for triggered locations,
    # and invokes the supervisor when risk conditions are met.
    #
    # make_supervisor_callback() returns a closure that captures the graph
    # and the results accumulator.  The EventLoop never sees the graph —
    # it just calls on_batch(batch).
    supervisor_results: list[tuple[int, dict]] = []
    on_batch = make_supervisor_callback(supervisor_graph, supervisor_results)
    event_loop = build_event_loop(location_store, on_batch)

    # ── STEP 7: Run pipeline and event loop concurrently ─────────────────────
    #
    # The pipeline produces data.  The event loop consumes it.
    # They share the location_store — that's the only coupling.
    # run_pipeline_with_event_loop handles lifecycle, cancellation,
    # and a final drain pass.
    await run_pipeline_with_event_loop(pipeline, event_loop, num_ticks=20)

    supervisor_result = supervisor_results[-1][1] if supervisor_results else {}

    # ── STEP 8: Print results ────────────────────────────────────────────────

    print()
    print("=" * 65)
    print("Pipeline complete")
    print(f"  World ticks:        {engine.current_tick}")
    print(f"  Supervisor calls:   {len(supervisor_results)}")
    print(f"  Invocation ticks:   {[t for t, _ in supervisor_results]}")
    print(f"  Event loop cycles:  {event_loop.cycles_completed}")
    print(f"  Locations in store: {location_store.get_all_location_ids()}")
    print("=" * 65)

    # Ground truth
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

    # Agent findings
    findings = supervisor_result.get("cluster_findings", [])
    print("AGENT FINDINGS")
    if not findings:
        print("  No anomalies detected.")
    else:
        for finding in findings:
            print(f"  [{finding['cluster_id']:15s}] {finding['anomaly_type']:20s} conf={finding['confidence']:.2f}")
            print(f"    {finding['summary']}")
            print(f"    Sensors: {finding['affected_sensors']}")

    # Cross-agent store
    print()
    print("CROSS-AGENT STORE CONTENTS")
    for cluster_id in ["cluster-north", "cluster-south"]:
        items = agent_store.search(("incidents", cluster_id))
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
    print(f"  Status:   {supervisor_result.get('status', 'n/a')}")
    print(f"  Summary:  {supervisor_result.get('situation_summary', 'none')}")
    print()

    commands = supervisor_result.get("pending_commands", [])
    print(f"  Commands issued: {len(commands)}")
    for cmd in commands:
        print(f"    [{cmd.priority}] {cmd.command_type:12s} cluster={cmd.cluster_id}")
        print(f"         payload: {cmd.payload}")

    # Preparedness evaluation
    print_preparedness_report(location_store, resource_inventory)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(main())
