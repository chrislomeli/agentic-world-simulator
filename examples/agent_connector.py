"""
agent_connector.py — STEP 03: Connect an LLM to the supervisor graph

select_llm() returns the LLM (or None for STUB mode) that the supervisor graph
will use when calling cluster agents.  Swap the commented lines to switch from
the deterministic stub to a real Claude or GPT-4 model.

STUB mode is the default: agents produce deterministic, repeatable output with
no API calls.  Useful for understanding the graph structure before adding a
real LLM.
"""

from config import Settings, LLMProvider

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: SETUP & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
def get_openai_llm(model_name: str, openai_api_key: str):
    # Option 2: Use OpenAI (requires OPENAI_API_KEY)
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=model_name, temperature=0,
                     api_key=openai_api_key)
    return llm

def get_anthropic_llm(model_name: str, anthropic_api_key: str):
    # Option 1: Use Claude (requires ANTHROPIC_API_KEY)
    from langchain_anthropic import ChatAnthropic
    llm = ChatAnthropic(model=model_name, temperature=0,
                        api_key=anthropic_api_key)
    return llm


def select_llm(settings: Settings):
    """
    Choose which LLM to use (or run in STUB mode with no LLM).

    For learning, STUB mode is fine. To use a real LLM, uncomment one option.
    """
    model_cfg = settings.selected_model
    if model_cfg is None or model_cfg.provider == LLMProvider.STUB:
        print("Running in STUB mode")
        return None, "STUB"

    if not model_cfg.api_key:
        raise ValueError(
            f"Missing API key for provider {model_cfg.provider.value}. "
            f"Expected env var mapped to settings field '{model_cfg.key_label}'."
        )

    if model_cfg.provider == LLMProvider.ANTHROPIC:
        llm = get_anthropic_llm(model_cfg.model, model_cfg.api_key)
    elif model_cfg.provider == LLMProvider.OPENAI:
        llm = get_openai_llm(model_cfg.model, model_cfg.api_key)
    else:
        llm = None

    mode = "LLM" if llm is not None else "STUB"
    print(f"Running in {mode} mode")
    return llm, mode