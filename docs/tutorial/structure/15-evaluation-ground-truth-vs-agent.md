# Session 15: Evaluation — Preparedness Assessment Quality

## Goal
Evaluate the quality of the supervisor's **preparedness assessments** across different scenarios. The question isn't "did the agent predict the fire?" — it's "did the agent correctly identify fire potential, assess resource readiness, and recommend appropriate responses?"

## Rubric Skills Introduced
- None new (evaluation layer on top of existing skills)

## Why Not Detection Accuracy?
Binary prediction ("fire will happen" / "fire won't") puts the agent in a win-lose position with no real ML model behind it. Preparedness assessment is different:
- **"High fire potential"** is always defensible given dry conditions and sensor data
- **"Cluster-south lacks helicopter coverage"** is a verifiable fact about resource state
- **False positives are caution**, not errors — exactly what preparedness should produce

Ground truth still matters — but as context for evaluating the assessment, not as a binary scorecard.

## Key Concepts
- **Fire potential assessment** — did the supervisor identify elevated risk from sensor conditions?
- **Resource gap analysis** — did it correctly identify which clusters are under-covered?
- **Recommendation quality** — did the commands match the resource gaps?
- **Degradation sensitivity** — did assessments change appropriately when conditions worsened?

## What You Build
1. Run full pipeline across multiple scenarios (from Session 14)
2. Collect supervisor assessments and commands from each run
3. Compare assessments against known resource state
4. Evaluate whether recommendations match the actual gaps

## What You Can Run
```python
from domains.wildfire import create_full_wildfire_scenario

def evaluate_assessment(label, resource_disable_frac=0.0):
    engine, resources = create_full_wildfire_scenario()

    if resource_disable_frac > 0:
        resources.disable_resources("firetruck", fraction=resource_disable_frac)

    # ... run full pipeline, collect supervisor result ...

    # Ground truth: what was the actual resource state?
    readiness = resources.readiness_summary()
    actual_gaps = []
    for cluster_id in ["cluster-north", "cluster-south"]:
        prep = resources.check_preparedness(cluster_id)
        if prep["gaps"]:
            actual_gaps.append((cluster_id, prep["gaps"]))

    # What did the supervisor assess?
    summary = result["situation_summary"]
    commands = result["pending_commands"]

    print(f"\n--- {label} ---")
    print(f"  Supervisor summary: {summary[:150]}")
    print(f"  Commands: {len(commands)}")
    for cmd in commands:
        print(f"    [{cmd.command_type}] → {cmd.cluster_id}")
    print(f"  Actual resource gaps: {actual_gaps}")

    # Evaluation: did the supervisor's assessment match reality?
    mentioned_gaps = any("gap" in summary.lower() or "unavailable" in summary.lower()
                        for _ in [1])
    print(f"  Mentioned gaps: {mentioned_gaps}")
    print(f"  Actual gaps exist: {len(actual_gaps) > 0}")
    if actual_gaps and not mentioned_gaps:
        print(f"  ⚠ MISS: gaps exist but supervisor didn't mention them")
    if mentioned_gaps and not actual_gaps:
        print(f"  ℹ Supervisor noted potential gaps (conservative — acceptable)")

evaluate_assessment("Baseline — full resources")
evaluate_assessment("50% firetrucks disabled", resource_disable_frac=0.5)
evaluate_assessment("All firetrucks disabled", resource_disable_frac=1.0)
```

## Evaluation Dimensions

| Dimension | What it measures | How to evaluate |
|-----------|-----------------|----------------|
| Risk identification | Did the agent note fire potential from sensor conditions? | Check situation_summary for risk language |
| Gap detection | Did it identify under-covered clusters? | Compare summary to check_preparedness() output |
| Recommendation quality | Do commands address the actual gaps? | Match command targets to clusters with gaps |
| Degradation sensitivity | Did assessment urgency increase as conditions worsened? | Compare summaries across scenarios |
| Conservative bias | Does it err on the side of caution? | False positives are acceptable; missed gaps are not |

## Key Files
- `src/world/generic_engine.py` — GenericGroundTruthSnapshot, engine.history
- `src/resources/inventory.py` — check_preparedness(), readiness_summary()
- `src/agents/supervisor/state.py` — SupervisorState (situation_summary, pending_commands)

## Verification
- Baseline: supervisor reports adequate preparedness (no gaps to find)
- Disabled firetrucks: supervisor identifies coverage gaps or recommends redeployment
- Full degradation: supervisor escalates with strongest urgency
- Assessment quality improves with more resource tools available
- Conservative bias: supervisor may flag potential issues even when none exist (acceptable)

## What You've Built
At this point you have a complete, runnable testbed:
- World engine with fire physics
- Noisy sensors with failure modes
- LangGraph cluster agents (stub + LLM)
- LangGraph supervisor with Send API fan-out
- Resources with preparedness querying
- Scenario knobs for resilience testing
- **Evaluation framework measuring preparedness assessment quality, not binary prediction**
