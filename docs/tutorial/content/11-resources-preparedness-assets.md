# Episode 3, Session 11: Resources — Preparedness Assets

> **What we're building:** A resource layer for preparedness assets (firetrucks, hospitals, helicopters) that live on the grid and can be queried by agents.
> **Why we need it:** Sessions 06–10 gave agents the ability to detect anomalies and decide on actions. But decisions need context: "Are we prepared for this situation?" Resources are queryable world state that help agents answer that question.
> **What you'll have at the end:** A ResourceInventory with firetrucks, hospitals, and other assets that you can query, deploy, consume capacity from, and manipulate with scenario knobs — all without any LLM integration yet (that comes in Session 12).

---

## Why resources are different from sensors

You've built sensors (Sessions 03–04). Resources might seem similar — both live on the grid, both have types and IDs. But they're fundamentally different:

**Sensors produce data:**
- Sensors emit `SensorEvent` objects every tick
- Sensors have failure modes (STUCK, DROPOUT, DRIFT)
- Sensors are active — they observe the world and report what they see

**Resources are data:**
- Resources don't emit events — they're queryable state
- Resources have status transitions (AVAILABLE → DEPLOYED → AVAILABLE)
- Resources are passive — agents query them to assess readiness

A firetruck doesn't "observe" anything. It exists at a location with a capacity (500 gallons of water). An agent queries the resource inventory: "How many firetrucks are available in cluster-south?" The inventory answers: "2 firetrucks, 1000 gallons total capacity, both AVAILABLE."

This is why `ResourceBase` is a Pydantic `BaseModel`, not an abstract class like `SensorBase`. Resources *are* data. They don't *produce* data.

---

## ResourceBase: the data model

Here's the complete resource model:

```python
class ResourceBase(BaseModel):
    # Identity
    resource_id: str                    # Unique ID, e.g. "firetruck-7"
    resource_type: str                  # Type tag, e.g. "firetruck", "hospital"
    cluster_id: str                     # Which cluster this belongs to
    
    # Operational state
    status: ResourceStatus = ResourceStatus.AVAILABLE
    
    # Location
    grid_row: int
    grid_col: int
    
    # Capacity
    capacity: float = 1.0               # Maximum capability
    available: float = 1.0              # Current remaining capability
    
    # Mobility
    mobile: bool = False                # Can this resource change position?
    
    # Domain extras
    metadata: Dict[str, Any] = {}       # Domain-specific fields
```

**ResourceStatus enum:**

```python
class ResourceStatus(str, Enum):
    AVAILABLE       = "AVAILABLE"        # Ready to deploy
    DEPLOYED        = "DEPLOYED"         # Currently in use at an incident
    EN_ROUTE        = "EN_ROUTE"         # Moving to a new location (mobile only)
    OUT_OF_SERVICE  = "OUT_OF_SERVICE"   # Broken, refueling, offline
```

**Status vs. capacity:**

These are deliberately separate:
- **Status** — operational state of the resource itself (is the firetruck running?)
- **Capacity** — maximum capability (500 gallons)
- **Available** — current remaining capability (300 gallons after use)

A hospital with 0 beds available is still `AVAILABLE` (it exists and is operational, just overloaded). The agent distinguishes "overloaded" from "closed" by checking both `status` and `available/capacity`.

**Mobility:**

Some resources are fixed (hospitals, fire stations). Others are mobile (firetrucks, helicopters). The `mobile` flag controls whether `deploy()` can update the grid position. Fixed resources can still be deployed (a hospital can be "deployed" to handle a surge) but their location doesn't change.

---

## Creating resources

Resources are created directly — no subclass required:

```python
from resources.base import ResourceBase, ResourceStatus

# Firetruck (mobile, capacity = gallons of water)
truck = ResourceBase(
    resource_id="firetruck-1",
    resource_type="firetruck",
    cluster_id="cluster-south",
    grid_row=7,
    grid_col=1,
    capacity=500.0,
    available=500.0,
    mobile=True,
    metadata={"unit": "gallons", "crew_size": 4, "model": "Type 1"},
)

# Hospital (fixed, capacity = beds)
hospital = ResourceBase(
    resource_id="hospital-central",
    resource_type="hospital",
    cluster_id="cluster-south",
    grid_row=8,
    grid_col=8,
    capacity=50.0,
    available=42.0,  # 8 beds occupied
    mobile=False,
    metadata={"unit": "beds", "trauma_level": 2},
)

# Helicopter (mobile, capacity = flight hours)
heli = ResourceBase(
    resource_id="heli-1",
    resource_type="helicopter",
    cluster_id="cluster-north",
    grid_row=2,
    grid_col=2,
    capacity=4.0,
    available=4.0,
    mobile=True,
    metadata={"unit": "flight_hours", "tank_gal": 700},
)
```

What "capacity" means is domain-specific. For a firetruck, it's gallons. For a hospital, it's beds. For a helicopter, it's flight hours. The `metadata["unit"]` field documents this for humans and tools.

---

## ResourceInventory: registration and queries

The `ResourceInventory` manages resources on the grid:

```python
from resources.inventory import ResourceInventory

inventory = ResourceInventory(grid_rows=10, grid_cols=10)

# Register resources
inventory.register(truck)
inventory.register(hospital)
inventory.register(heli)

print(f"Total resources: {inventory.size}")  # 3
```

**Queries:**

```python
# By type
firetrucks = inventory.by_type("firetruck")
print(f"Firetrucks: {len(firetrucks)}")  # 1

# By cluster
south_resources = inventory.by_cluster("cluster-south")
print(f"Cluster-south resources: {len(south_resources)}")  # 2 (truck + hospital)

# By status
available = inventory.by_status(ResourceStatus.AVAILABLE)
print(f"Available: {len(available)}")  # 3

# At a position
at_station = inventory.get_resources_at(row=7, col=1)
print(f"At (7,1): {[r.resource_id for r in at_station]}")  # ['firetruck-1']

# All types and clusters
print(f"Types: {inventory.resource_types()}")  # {'firetruck', 'hospital', 'helicopter'}
print(f"Clusters: {inventory.cluster_ids()}")  # {'cluster-south', 'cluster-north'}
```

**Readiness summary:**

```python
summary = inventory.readiness_summary()
print(summary)
```

Output:

```python
{
    "total_resources": 3,
    "by_type": {
        "firetruck": {
            "total": 1,
            "available": 1,
            "deployed": 0,
            "out_of_service": 0,
            "total_capacity": 500.0,
            "available_capacity": 500.0,
        },
        "hospital": {
            "total": 1,
            "available": 1,
            "deployed": 0,
            "out_of_service": 0,
            "total_capacity": 50.0,
            "available_capacity": 42.0,
        },
        "helicopter": {
            "total": 1,
            "available": 1,
            "deployed": 0,
            "out_of_service": 0,
            "total_capacity": 4.0,
            "available_capacity": 4.0,
        },
    },
    "by_cluster": {
        "cluster-south": {
            "total": 2,
            "available": 2,
            "types": ["firetruck", "hospital"],
        },
        "cluster-north": {
            "total": 1,
            "available": 1,
            "types": ["helicopter"],
        },
    },
    "by_status": {
        "AVAILABLE": 3,
    },
}
```

This is the data structure that agents will query to assess preparedness.

**Coverage by cluster:**

```python
coverage = inventory.coverage_by_cluster()
print(coverage)
# {'cluster-south': ['firetruck', 'hospital'], 'cluster-north': ['helicopter']}
```

Useful for identifying clusters with no fire coverage, no medical resources, etc.

---

## Status transitions and capacity management

Resources have a state machine for status transitions:

**Deploy:**

```python
# Deploy the firetruck to a fire at (5, 3)
inventory.deploy("firetruck-1", row=5, col=3)
print(truck.status)       # DEPLOYED
print(truck.grid_row)     # 5 (moved because mobile=True)
print(truck.grid_col)     # 3
```

For mobile resources, `deploy()` updates the position. For fixed resources, the position stays the same.

**Consume capacity:**

```python
# Use 200 gallons of water
consumed = truck.consume(200.0)
print(consumed)           # 200.0
print(truck.available)    # 300.0 (500 - 200)
print(truck.utilization)  # 0.4 (40% used)
```

`consume()` returns the actual amount consumed (may be less than requested if `available < amount`). It never goes below 0.

**Restore capacity:**

```python
# Refill the truck
restored = truck.restore(500.0)
print(restored)           # 200.0 (only 200 headroom)
print(truck.available)    # 500.0 (back to full)
```

`restore()` returns the actual amount restored (capped at `capacity`). It never exceeds capacity.

**Release:**

```python
# Release the truck back to AVAILABLE
inventory.release("firetruck-1")
print(truck.status)       # AVAILABLE
```

**Disable:**

```python
# Take the truck out of service (maintenance, breakdown)
truck.disable()
print(truck.status)       # OUT_OF_SERVICE
```

Once `OUT_OF_SERVICE`, the resource can't be deployed until it's released.

---

## Scenario knobs: degradation and restoration

The inventory provides experimental knobs to manipulate resources:

**Reduce resources (budget constraints):**

```python
# Remove 50% of firetrucks
removed = inventory.reduce_resources("firetruck", keep_fraction=0.5)
print(f"Removed: {removed}")  # ['firetruck-1'] (if there were 2, 1 would remain)
```

This randomly removes resources of a type. Useful for testing agent behavior under resource scarcity.

**Disable resources (equipment failure):**

```python
# Set 30% of helicopters to OUT_OF_SERVICE
disabled = inventory.disable_resources("helicopter", fraction=0.3)
print(f"Disabled: {disabled}")  # ['heli-1'] (if there were 3, ~1 would be disabled)
```

This randomly sets resources to `OUT_OF_SERVICE`. Useful for testing agent resilience to equipment failure.

**Reset all:**

```python
# Reset all resources to AVAILABLE and restore full capacity
inventory.reset_all()
```

This is the "undo" button for scenario knobs.

---

## Pre-built wildfire scenario

The wildfire domain includes a pre-built resource scenario with NWCG-aligned assets:

```python
from domains.wildfire import create_full_wildfire_scenario

engine, resource_inventory = create_full_wildfire_scenario()

summary = resource_inventory.readiness_summary()
print(f"Total resources: {summary['total_resources']}")
print(f"By type: {list(summary['by_type'].keys())}")
```

The scenario includes 8 resources across 2 clusters:

| Resource ID | Type | Cluster | Capacity | Mobile | Notes |
|-------------|------|---------|----------|--------|-------|
| crew-south-1 | crew | cluster-south | 15.0 ch/hr | False | Interagency Hotshot Crew (NWCG C-1) |
| crew-south-2 | crew | cluster-south | 8.0 ch/hr | False | Hand Crew (NWCG C-2) |
| engine-south-1 | engine | cluster-south | 500.0 gal | True | Wildland Engine 4x4 (NWCG E-3) |
| engine-south-2 | engine | cluster-south | 500.0 gal | True | Wildland Engine 4x4 (NWCG E-3) |
| dozer-south-1 | dozer | cluster-south | 60.0 ch/hr | True | Heavy Dozer (NWCG D-1) |
| ambulance-1 | ambulance | cluster-south | 2.0 patients | True | 2-patient ambulance |
| hospital-1 | hospital | cluster-south | 50.0 beds | False | 50-bed hospital (42 available) |
| heli-1 | helicopter | cluster-north | 700.0 gal | True | Heavy Helicopter (NWCG H-1) |

**NWCG alignment:**

The National Wildfire Coordinating Group (NWCG) defines standard resource types and capabilities. The pre-built scenario uses NWCG IDs in metadata:

```python
crew = resource_inventory.get_resource("crew-south-1")
print(crew.metadata)
# {
#   "nwcg_id": "C-1",
#   "nwcg_name": "Interagency Hotshot Crew",
#   "production_rate_chains_hr": 15.0,
#   "unit": "chains/hour",
# }
```

This makes the resources grounded in real-world wildfire response standards.

---

## Running it

Here's a complete script that creates resources, queries them, and manipulates them:

```python
from resources.base import ResourceBase, ResourceStatus
from resources.inventory import ResourceInventory

# Create inventory
inventory = ResourceInventory(grid_rows=10, grid_cols=10)

# Create resources
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
    capacity=50.0, available=42.0, mobile=False,
    metadata={"unit": "beds"},
)
inventory.register(hospital)

# Query
print(f"Total: {inventory.size}")
print(f"Coverage: {inventory.coverage_by_cluster()}")
print(f"Readiness: {inventory.readiness_summary()}")

# Deploy the truck
inventory.deploy("firetruck-1", row=5, col=3)
print(f"\nTruck status: {truck.status}")  # DEPLOYED
print(f"Truck position: ({truck.grid_row}, {truck.grid_col})")  # (5, 3)

# Consume capacity
truck.consume(200)
print(f"Water: {truck.available}/{truck.capacity}")  # 300.0/500.0

# Release
inventory.release("firetruck-1")
print(f"Truck status: {truck.status}")  # AVAILABLE

# Scenario knobs
print(f"\nBefore disable: {inventory.by_status(ResourceStatus.AVAILABLE)}")
inventory.disable_resources("firetruck", fraction=1.0)
print(f"After disable: {inventory.by_status(ResourceStatus.OUT_OF_SERVICE)}")

inventory.reset_all()
print(f"After reset: {inventory.by_status(ResourceStatus.AVAILABLE)}")
```

**Expected output:**

```
Total: 2
Coverage: {'cluster-south': ['firetruck', 'hospital']}
Readiness: {'total_resources': 2, 'by_type': {...}, 'by_cluster': {...}, 'by_status': {'AVAILABLE': 2}}

Truck status: DEPLOYED
Truck position: (5, 3)
Water: 300.0/500.0
Truck status: AVAILABLE

Before disable: [ResourceBase(id='firetruck-1', ...), ResourceBase(id='hospital-central', ...)]
After disable: [ResourceBase(id='firetruck-1', ...)]
After reset: [ResourceBase(id='firetruck-1', ...), ResourceBase(id='hospital-central', ...)]
```

---

## What you learned: Resource layer patterns

This session introduced the resource layer:

**1. Resources are data, not behavior** — `ResourceBase` is a Pydantic `BaseModel`, not an abstract class. Resources don't emit events or tick.

**2. Status vs. capacity** — status is operational state (AVAILABLE, DEPLOYED, etc.), capacity is capability (gallons, beds, etc.). They're separate concerns.

**3. Mobile vs. fixed** — mobile resources can change position via `deploy()`, fixed resources can't.

**4. ResourceInventory** — mirrors `SensorInventory` pattern: registration, queries, status transitions, readiness summaries.

**5. Scenario knobs** — `reduce_resources()`, `disable_resources()`, `reset_all()` for experimental manipulation.

**6. NWCG alignment** — pre-built wildfire resources use real-world NWCG standards for grounded simulation.

Resources are queryable world state. Agents don't control resources directly (no actuators yet). They query the inventory to assess preparedness: "Do we have enough firetrucks? Are any hospitals overloaded?"

---

## Key files

- `src/resources/base.py` — `ResourceBase` Pydantic model, `ResourceStatus` enum, state transitions, capacity management
- `src/resources/inventory.py` — `ResourceInventory` class, registration, queries, readiness summaries, scenario knobs
- `src/domains/wildfire/scenarios.py` — `create_wildfire_resources()`, `create_full_wildfire_scenario()`
- `src/domains/wildfire/nwcg_resources.py` — NWCG catalog, resource definitions

---

*Next: Session 12 wires resource tools into the supervisor agent. The LLM will be able to call `get_resources_by_cluster()`, `check_resource_availability()`, and other tools to assess preparedness during the assess and decide loops. This completes the supervisor's context: findings (what happened) + resources (are we prepared) → decisions (what to do).*
