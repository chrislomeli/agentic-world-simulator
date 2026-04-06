# Session 11: Resources — Preparedness Assets

## Goal
Build ResourceBase instances, manage them with ResourceInventory, query readiness, and experiment with scenario knobs. No agents — just the resource layer in isolation.

## Rubric Skills Introduced
- None (domain layer — no LangGraph yet)

## Key Concepts
- **ResourceBase (Pydantic BaseModel)** — resources *are* data, not behavior. No subclass required.
- **ResourceStatus enum** — AVAILABLE, DEPLOYED, EN_ROUTE, OUT_OF_SERVICE
- **Capacity vs. status** — a hospital with 0 beds is still AVAILABLE (operational but overloaded)
- **Mobile vs. fixed** — firetrucks move, hospitals don't
- **ResourceInventory** — mirrors SensorInventory: registration, queries, readiness summaries
- **Scenario knobs** — reduce_resources(), disable_resources(), reset_all()

## What You Build
1. Create ResourceBase instances (firetruck, hospital, helicopter)
2. Register them in a ResourceInventory
3. Query by type, cluster, status, grid position
4. Get a readiness_summary() and coverage_by_cluster()
5. Use scenario knobs to degrade and restore

## What You Can Run
```python
from resources.base import ResourceBase, ResourceStatus
from resources.inventory import ResourceInventory

inventory = ResourceInventory(grid_rows=10, grid_cols=10)

# Create and register resources
truck = ResourceBase(
    resource_id="firetruck-1", resource_type="firetruck",
    cluster_id="cluster-south", grid_row=7, grid_col=1,
    capacity=500.0, available=500.0, mobile=True,
    metadata={"unit": "gallons"},
)
inventory.register(truck)

hospital = ResourceBase(
    resource_id="hospital-central", resource_type="hospital",
    cluster_id="cluster-south", grid_row=8, grid_col=8,
    capacity=50.0, available=50.0, mobile=False,
)
inventory.register(hospital)

# Query
print(f"Total: {inventory.size}")
print(f"By cluster: {inventory.coverage_by_cluster()}")
print(f"Readiness: {inventory.readiness_summary()}")

# Status transitions
truck.deploy(row=5, col=3)
print(f"Truck status: {truck.status}")  # DEPLOYED

truck.consume(200)
print(f"Water: {truck.available}/{truck.capacity}")  # 300/500

truck.release()
print(f"Truck status: {truck.status}")  # AVAILABLE

# Scenario knobs
inventory.disable_resources("firetruck", fraction=0.5)
print(f"After disable: {inventory.readiness_summary()}")

inventory.reset_all()
print(f"After reset: {inventory.readiness_summary()}")
```

**Or use the pre-built scenario:**
```python
from domains.wildfire import create_full_wildfire_scenario

engine, resources = create_full_wildfire_scenario()
print(resources.readiness_summary())
```

## Key Files
- `src/resources/base.py` — ResourceBase, ResourceStatus
- `src/resources/inventory.py` — ResourceInventory
- `src/domains/wildfire/scenarios.py` — create_wildfire_resources(), create_full_wildfire_scenario()

## Verification
- Resources register and query correctly
- Status transitions follow the state machine (can't deploy OUT_OF_SERVICE)
- Capacity consume/restore respects bounds
- Scenario knobs degrade and restore as expected
- Pre-built wildfire resources include 5 assets across 2 clusters

## Next Session
Session 12 wires resource tools into the supervisor so the LLM can query preparedness.
