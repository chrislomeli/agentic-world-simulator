"""
agent_connector.py — STEP 03: Connect an LLM to the supervisor graph

select_llm() returns the LLM (or None for STUB mode) that the supervisor graph
will use when calling cluster agents.  Swap the commented lines to switch from
the deterministic stub to a real Claude or GPT-4 model.

STUB mode is the default: agents produce deterministic, repeatable output with
no API calls.  Useful for understanding the graph structure before adding a
real LLM.
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

def select_llm(settings):
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