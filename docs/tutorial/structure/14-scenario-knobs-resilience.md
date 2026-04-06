# Session 14: Scenario Knobs — Resilience Testing

## Goal
Run the same fire scenario under different conditions: degraded sensors, reduced resources, equipment failures. Compare agent performance across scenarios.

## Rubric Skills Introduced
- None new (applies skills from previous sessions under stress)

## Key Concepts
- **Sensor knobs** — thin_sensors() removes sensors; inject_failures() causes intermittent drops
- **Resource knobs** — reduce_resources() removes assets; disable_resources() sets OUT_OF_SERVICE
- **Controlled experiments** — same random seed, same fire, different conditions
- **Performance comparison** — findings count, detection latency, false positive rate

## What You Build
1. Baseline run: full sensors, full resources
2. Degraded sensors: thin 50% of sensors
3. Degraded resources: disable 50% of firetrucks
4. Combined degradation: both sensors and resources reduced
5. Compare findings across runs

## What You Can Run
```python
import random
from domains.wildfire import create_full_wildfire_scenario

def run_scenario(label, sensor_thin=1.0, resource_disable_frac=0.0):
    random.seed(42)  # Same fire every time
    engine, resources = create_full_wildfire_scenario()

    if resource_disable_frac > 0:
        resources.disable_resources("firetruck", fraction=resource_disable_frac)

    # ... (run full pipeline from Session 13)
    # ... collect findings

    print(f"\n--- {label} ---")
    print(f"  Findings: {len(findings)}")
    print(f"  Resources available: {resources.readiness_summary()['by_status']}")

run_scenario("Baseline")
run_scenario("50% firetrucks disabled", resource_disable_frac=0.5)
run_scenario("All firetrucks disabled", resource_disable_frac=1.0)
```

## Experiment Matrix

| Scenario | Sensors | Resources | Expected Behavior |
|----------|---------|-----------|-------------------|
| Baseline | 100% | 100% | Full detection, adequate preparedness |
| Blind spots | 50% thinned | 100% | Missed detections, delayed findings |
| Under-resourced | 100% | 50% disabled | Detection OK, preparedness gaps |
| Worst case | 50% thinned | 50% disabled | Both detection and response degraded |

## Key Questions to Answer
- Does thinning sensors cause the agent to miss fires?
- Does disabling resources change the supervisor's recommendations?
- How does the LLM's confidence change with degraded inputs?
- Does check_preparedness correctly identify gaps?

## Key Files
- `src/world/sensor_inventory.py` — thin_sensors(), inject_failures()
- `src/resources/inventory.py` — reduce_resources(), disable_resources(), reset_all()

## Verification
- Baseline produces the most findings
- Thinned sensors produce fewer findings (some fires missed)
- Disabled resources show up in check_preparedness gaps
- Combined degradation produces the worst results

## Next Session
Session 15 formally compares ground truth to agent findings for evaluation.
