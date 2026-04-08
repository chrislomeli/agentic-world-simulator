#!/usr/bin/env python3


import asyncio
import logging
import os
import random

import langsmith
from langgraph.store.memory import InMemoryStore

from agents.supervisor.graph import build_supervisor_graph
from bridge.consumer import EventBridgeConsumer
from config import get_settings, Settings
from domains.wildfire.sampler import sample_local_conditions
from domains.wildfire.scenario_loader import load_scenario_from_json
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

def configure_environment() -> Settings:
    """
    Load API keys, configure logging, set up LangSmith tracing.

    Think of this as: "open the door, turn on the lights, get your tools ready"
    """
    os.environ.setdefault("AI_ENV_FILE", "/Users/chrislomeli/Source/SECRETS/.env")
    settings = get_settings()  # Load .env file (API keys, project names, etc.)
    settings.apply_langsmith()  # Enable LangSmith tracing for debugging agent calls
    settings.world_data = "/Users/chrislomeli/Source/PROJECTS/agenticAI/agentic-world-simulator/src/domains/wildfire/scenario_data/north_south_fire.json"
    settings.llm = None

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
    print(settings.model_dump_json(indent=2))
    return settings

# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
async def main():
    """
    The main pipeline orchestrator.

    Flow:
    1. Set up the world (wildfire engine on a grid)
    2. Place sensors in the world (sensors are pure devices — no engine reference)
    3. Run the event loop: publisher samples conditions → sensors emit → queue collects
    4. Consumer groups events by cluster
    5. Supervisor fans out to cluster agents, correlates, decides
    6. Print results
    """

    # ───────────────────────────────────────────────────────────────────────────
    # STEP 1: INITIALIZE
    # ───────────────────────────────────────────────────────────────────────────

    settings = configure_environment()


if __name__ == "__main__":
    # asyncio.run() starts the async event loop and runs main()
    asyncio.run(main())
