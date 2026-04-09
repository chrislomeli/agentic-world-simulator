#!/usr/bin/env python3
"""
config_builder.py — STEP 01: Environment setup & configuration

Load API keys from .env, configure logging, and enable LangSmith tracing.
This is the first thing every other step calls — get the environment ready
before touching the world engine or any agents.

The main() here is just a smoke-test: call configure_environment() and verify
the settings load without errors.
"""

import asyncio
import logging
import os
from typing import Dict

from config import get_settings, Settings, LLMLabel, LLMModel, LLMProvider

models: Dict[LLMLabel, LLMModel|None] = {
    LLMLabel.HAIKU: LLMModel(key_label="anthropic_api_key", provider=LLMProvider.ANTHROPIC, model="claude-haiku-4-5-20251001"),
    LLMLabel.SONNET: LLMModel(key_label="anthropic_api_key", provider=LLMProvider.ANTHROPIC, model="claude-sonnet-4-6"),
    LLMLabel.GPT_MINI: LLMModel(key_label="openai_api_key", provider=LLMProvider.OPENAI, model="gpt-5.4-mini"),
    LLMLabel.GPT_NANO: LLMModel(key_label="openai_api_key", provider=LLMProvider.OPENAI, model="gpt-5.4-nano"),
    LLMLabel.GPT: LLMModel(key_label="openai_api_key", provider=LLMProvider.OPENAI, model="gpt-5.4"),
    LLMLabel.STUB: None
}


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _redacted_settings_json(settings: Settings) -> str:
    payload = settings.model_dump(mode="json")
    for key in ("anthropic_api_key", "openai_api_key", "langchain_api_key"):
        if key in payload:
            payload[key] = _mask_secret(payload.get(key, ""))
    llm_model = payload.get("llm_model")
    if isinstance(llm_model, dict) and "api_key" in llm_model:
        llm_model["api_key"] = _mask_secret(llm_model.get("api_key") or "")
    import json
    return json.dumps(payload, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: SETUP & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
literals = {
    "AI_ENV_FILE": "/Users/chrislomeli/Source/SECRETS/.env",
    "WORLD_DATA": "/Users/chrislomeli/Source/PROJECTS/agenticAI/agentic-world-simulator/src/domains/wildfire/scenario_data/north_south_fire.json",
    "USE_MODEL": LLMLabel.STUB
}

def configure_environment() -> Settings:
    """
    Load API keys, configure logging, set up LangSmith tracing.

    Think of this as: "open the door, turn on the lights, get your tools ready"
    """
    os.environ.setdefault("AI_ENV_FILE", literals["AI_ENV_FILE"])
    settings = get_settings()  # Load .env file (API keys, project names, etc.)
    settings.apply_langsmith()  # Enable LangSmith tracing for debugging agent calls
    settings.world_data = literals["WORLD_DATA"]
    connection = models.get(literals["USE_MODEL"], models[LLMLabel.GPT_MINI])
    settings.llm_model = connection
    settings.llm_source = connection.provider if connection else LLMProvider.STUB


    # Set up Python logging so we can see what's happening
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-35s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy HTTP logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Print what we're using (redacted)
    print(_redacted_settings_json(settings))
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
