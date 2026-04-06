# Session 15: Evaluation — Ground Truth vs. Agent

## Goal
Compare what actually happened (ground truth snapshots) with what the agent detected (findings). Compute detection accuracy, false positive rate, and response latency.

## Rubric Skills Introduced
- None new (evaluation layer on top of existing skills)

## Key Concepts
- **GenericGroundTruthSnapshot** — tick-by-tick record of actual world state
- **engine.history** — list of all snapshots from the run
- **AnomalyFinding** — what the agent detected
- **Metrics** — true positives, false positives, missed detections, detection delay

## What You Build
1. Run a full pipeline (from Session 13)
2. Extract ground truth from engine.history
3. Extract agent findings from the pipeline
4. Compare: which fires were detected? which were missed?
5. Compute basic metrics

## What You Can Run
```python
from domains.wildfire import create_full_wildfire_scenario

engine, resources = create_full_wildfire_scenario()

# ... run full pipeline, collect findings ...

# Ground truth: when did fires start?
fire_ticks = []
for snapshot in engine.history:
    burning = snapshot.grid_summary.get("BURNING", 0)
    if burning > 0:
        fire_ticks.append(snapshot.tick)

print(f"Fire active from tick {min(fire_ticks)} to {max(fire_ticks)}")
print(f"Peak burning cells: {max(s.grid_summary.get('BURNING', 0) for s in engine.history)}")

# Agent findings: when did agents detect anomalies?
detection_ticks = [f["raw_context"].get("trigger_event_id") for f in findings]
print(f"Agent produced {len(findings)} findings")

# Basic metrics
total_burning_ticks = len(fire_ticks)
detected_count = len(findings)
print(f"Detection rate: {detected_count}/{total_burning_ticks} ticks with active fire")

# Resource utilization at end
summary = resources.readiness_summary()
for rtype, info in summary["by_type"].items():
    util = 1 - (info["available_capacity"] / info["total_capacity"]) if info["total_capacity"] > 0 else 0
    print(f"  {rtype}: {util:.0%} utilized")
```

## Evaluation Dimensions

| Metric | What it measures | How to compute |
|--------|-----------------|----------------|
| Detection rate | % of fire ticks with at least one finding | findings / burning ticks |
| False positive rate | Findings when no fire exists | findings with no corresponding ground truth |
| Detection latency | Ticks between fire start and first finding | first finding tick - first burning tick |
| Resource awareness | Did supervisor mention resources? | Check situation_summary for resource references |
| Decision quality | Did commands match the situation? | Manual review of ActuatorCommands vs. ground truth |

## Key Files
- `src/world/generic_engine.py` — GenericGroundTruthSnapshot, engine.history
- `src/agents/cluster/state.py` — AnomalyFinding (raw_context contains trigger info)

## Verification
- Ground truth shows fire starting and spreading
- Agent findings correlate with actual fire activity
- Detection latency is measurable (not zero — sensors are noisy)
- Degraded scenarios (from Session 14) show worse metrics

## What You've Built
At this point you have a complete, runnable testbed:
- World engine with fire physics
- Noisy sensors with failure modes
- LangGraph cluster agents (stub + LLM)
- LangGraph supervisor with Send API fan-out
- Resources with preparedness querying
- Scenario knobs for resilience testing
- Evaluation framework for measuring agent quality
