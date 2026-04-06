# Session 14: Scenario Knobs — Preparedness Under Stress

## Goal
Run the same fire-potential scenario under different conditions: degraded sensors, reduced resources, equipment failures. Compare how the supervisor's **preparedness assessment** changes — not whether it "predicted" correctly, but whether it identified the right gaps and recommended the right responses.

## Rubric Skills Introduced
- None new (applies skills from previous sessions under stress)

## Why Preparedness, Not Prediction
The agent isn't trying to predict whether a fire will happen — that's a binary win/lose with no training data behind it. Instead, the agent assesses **fire potential** based on sensor conditions and evaluates whether **resources are positioned and available** to respond. This framing is:
- **Always defensible** — "high fire potential due to low humidity" is correct whether or not a fire starts
- **Demo-safe** — false positives are caution, not errors
- **Useful** — the value is in the gap analysis, not the prediction

## Key Concepts
- **Sensor knobs** — thin_sensors() removes sensors; inject_failures() causes intermittent drops
- **Resource knobs** — reduce_resources() removes assets; disable_resources() sets OUT_OF_SERVICE
- **Controlled experiments** — same random seed, same conditions, different preparedness levels
- **Assessment comparison** — how does the supervisor's preparedness assessment change under degradation?

## What You Build
1. Baseline run: full sensors, full resources → supervisor assesses preparedness
2. Degraded sensors: thin 50% → does the supervisor note reduced visibility?
3. Degraded resources: disable 50% of firetrucks → does it identify coverage gaps?
4. Combined degradation → does it escalate urgency appropriately?
5. Compare supervisor summaries and recommendations across runs

## What You Can Run
```python
import random
from domains.wildfire import create_full_wildfire_scenario

def run_scenario(label, sensor_thin=1.0, resource_disable_frac=0.0):
    random.seed(42)  # Same conditions every time
    engine, resources = create_full_wildfire_scenario()

    if resource_disable_frac > 0:
        resources.disable_resources("firetruck", fraction=resource_disable_frac)

    # ... (run full pipeline from Session 13)
    # ... collect findings and supervisor result

    print(f"\n--- {label} ---")
    print(f"  Sensor findings: {len(findings)}")
    print(f"  Supervisor summary: {result['situation_summary'][:120]}")
    print(f"  Commands issued: {len(result['pending_commands'])}")
    print(f"  Preparedness:")
    for gap in resources.check_preparedness_all():
        if gap["gaps"]:
            print(f"    ⚠ {gap['cluster_id']}: {gap['gaps']}")

run_scenario("Baseline — full preparedness")
run_scenario("50% firetrucks disabled", resource_disable_frac=0.5)
run_scenario("All firetrucks disabled", resource_disable_frac=1.0)
```

## Experiment Matrix

| Scenario | Sensors | Resources | What supervisor should assess |
|----------|---------|-----------|-------------------------------|
| Baseline | 100% | 100% | Fire potential noted, resources adequate |
| Blind spots | 50% thinned | 100% | Reduced confidence, may note limited visibility |
| Under-resourced | 100% | 50% disabled | Fire potential clear, coverage gaps identified |
| Worst case | 50% thinned | 50% disabled | Limited visibility AND coverage gaps — should escalate |

## Key Questions to Answer
- Does the supervisor's preparedness assessment correctly reflect available resources?
- With fewer sensors, does the supervisor express lower confidence or note visibility gaps?
- With disabled firetrucks, does `check_preparedness` identify the gap?
- Does the supervisor recommend different actions (escalate, redeploy) under degraded conditions?

## Key Files
- `src/world/sensor_inventory.py` — thin_sensors(), inject_failures()
- `src/resources/inventory.py` — reduce_resources(), disable_resources(), reset_all()

## Verification
- Baseline: supervisor reports adequate preparedness
- Disabled resources: check_preparedness shows gaps in affected clusters
- Supervisor recommendations change with degradation (more escalation, redeployment requests)
- Combined degradation triggers the strongest response

## Next Session
Session 15 evaluates the quality of the supervisor's preparedness assessments.
