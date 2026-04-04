# Wildfire Agent Testbed — Full Design Document

## Overview

An event-driven autonomous multi-agent system that monitors a simulated wildfire sensor
network, assesses risk, manages logistics, and makes escalation decisions under uncertainty.

Built on **LangGraph + Temporal + Kafka** with a simulated world engine, mock sensors,
and mock actuators. Designed as a learning platform and publishable demo — not a product.

### Goals
1. Deep proficiency with LangGraph — all major patterns
2. Publishable demo demonstrating production-grade agentic AI architecture
3. Platform for future neural net integration (see Phase 2)

### The core thesis
The event trigger is always discrete and code-handled. The LLM sits at decision nodes
where branching requires judgment over a space that cannot be fully enumerated in advance.
Code does what code is good at. LLMs do what LLMs are good at. Neither pretends to be the other.

---

## Architecture Overview

```
/core
  /world_engine       ← simulation ground truth
  /sensors            ← sensor base class + types
  /actuators          ← actuator base class + types
  /transport          ← Kafka topics, schemas, bridge consumer
  /agents             ← LangGraph subgraphs + Temporal workflows
  /memory             ← Postgres checkpointer + pgvector store
/scenarios
  /wildfire           ← scenario scripts + sensor configs
  /ocean_buoys        ← future skin
  /auv_fleet          ← future skin
  /icu                ← future skin
/docs
/scripts
```

The architecture is domain-agnostic. Scenarios are skins. The core 80% of the codebase
is identical across all scenario domains.

---

## Domain: Wildfire / Environmental Sensor Network

Chosen because:
- Immediately legible to any audience — no domain expertise required
- Decisions are genuinely hard in ways that resist enumeration
- Multi-agent topology is natural — geographic clusters, specialist agents, supervisor
- Actuators are clean and visible — alert dispatch, drone tasking, human escalation
- Mock data is easy to generate with controllable scenarios
- The README writes itself

### Alternative skins (same architecture)
- Ocean buoy network
- Autonomous underwater vehicle fleet
- ICU patient monitoring

---

## Where LLMs Earn Their Place

The test: can you write an exhaustive if/else tree for this decision? If yes, write code.
If the answer is "it depends on context in ways I can't fully enumerate" — that's the LLM.

| Role | Why LLM, not code |
|------|-------------------|
| Anomaly classification | Long tail of patterns that resist enumeration |
| Cross-sensor correlation | "Are these three weak signals a real event or noise?" |
| Significance assessment | "Did conditions change in a way that matters?" |
| Situation reporting | Human-readable narrative from structured data |
| Dynamic planning | Next steps depend on what was found — unknown in advance |
| Logistics reasoning | "Do we have enough resources given spread rate and terrain?" |

---

## Component 1: World Engine

The simulation ground truth. Agents never see it directly. The gap between world truth
and sensor observations is where all interesting agent behavior lives.

### Sub-components

| Component | Responsibility |
|-----------|----------------|
| World state | Entities with positions and properties |
| Sim clock | Tick system with time warp and pause/resume |
| Scenario scripts | Inject events — fires, sensor failures, weather changes |
| Physics models | Simple spread / diffusion / drift |

### Grid model

```python
# 5x5 grid is sufficient for a compelling demo
WORLD_GRID = {
    "A1": {
        "terrain": "chaparral",
        "elevation": "ridge",
        "population": "none",
        "adjacent": ["A2", "B1"]
    },
    "B2": {
        "terrain": "mixed_forest",
        "elevation": "slope",
        "population": "rural",
        "adjacent": ["A2", "B1", "B3", "C2"]
    },
    "C3": {
        "terrain": "grassland",
        "elevation": "valley",
        "population": "suburban",   # ← creates urgency
        "adjacent": ["B3", "C2", "C4", "D3"]
    }
}
```

### Fire spread

```python
def spread_fire(burning_sectors, wind_direction, wind_speed):
    new_burning = set()
    for sector in burning_sectors:
        for adjacent in WORLD_GRID[sector]["adjacent"]:
            spread_probability = calculate_spread_prob(
                terrain=WORLD_GRID[adjacent]["terrain"],
                wind_direction=wind_direction,
                wind_speed=wind_speed
            )
            if random.random() < spread_probability:
                new_burning.add(adjacent)
    return burning_sectors | new_burning
```

No real physics. No GIS library. Completely controllable. The demo value is in the
agent reasoning, not the simulation accuracy.

### Sim clock

```python
class SimClock:
    def __init__(self, tick_interval_seconds=5, time_warp=1.0):
        self.tick = 0
        self.tick_interval = tick_interval_seconds
        self.time_warp = time_warp  # >1.0 speeds up simulation
        self.paused = False

    async def run(self, world_state, scenario):
        while True:
            if not self.paused:
                scenario.apply_tick(world_state, self.tick)
                world_state.physics_step()
                self.tick += 1
            await asyncio.sleep(self.tick_interval / self.time_warp)
```

### Scenario scripts

Scenarios are the controllable drama engine. Each one is a sequence of injections
into world state at specific ticks.

```python
class WildfireScenario:
    """
    T=0:   Conditions nominal
    T=10:  Wind shift begins, humidity starts dropping
    T=20:  Ignition in sector B2
    T=30:  Fire spreads to B3, wind accelerates
    T=45:  C3 (suburban) threatened — resource margin is 12 minutes
    T=60:  If pre-positioned: containment possible
           If not pre-positioned: mutual aid required
    """
    def apply_tick(self, world_state, tick):
        if tick == 10:
            world_state.set_wind(direction="NE", speed=28)
            world_state.set_humidity_trend(delta_per_tick=-0.8)
        if tick == 20:
            world_state.ignite_sector("B2")
        if tick == 30:
            world_state.set_wind(speed=35)
        # etc.
```

The 12-minute margin is engineered deliberately. The demo is most compelling when
the agent's decision visibly changes the outcome.

---

## Component 2: Sensor Layer

Sensors sample from the world engine and publish events to Kafka.

### Sensor base class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import random

@dataclass
class SensorEvent:
    event_id: str
    sensor_id: str
    sensor_type: str
    cluster_id: str
    timestamp: datetime
    sim_tick: int
    value: float | dict
    confidence: float       # 0.0-1.0
    metadata: dict

class SensorBase(ABC):
    def __init__(self, sensor_id, cluster_id, noise_std=0.5):
        self.sensor_id = sensor_id
        self.cluster_id = cluster_id
        self.noise_std = noise_std
        self.failure_mode = None

    def sample(self, world_state, tick) -> SensorEvent:
        if self.failure_mode:
            return self._apply_failure(world_state, tick)

        raw_value = self._read_world(world_state)
        noisy_value = raw_value + random.gauss(0, self.noise_std)

        return SensorEvent(
            event_id=str(uuid4()),
            sensor_id=self.sensor_id,
            sensor_type=self.sensor_type,
            cluster_id=self.cluster_id,
            timestamp=datetime.utcnow(),
            sim_tick=tick,
            value=noisy_value,
            confidence=self._compute_confidence(),
            metadata={}
        )

    @abstractmethod
    def _read_world(self, world_state) -> float:
        pass
```

### Failure modes

```python
class FailureMode(Enum):
    STUCK = "stuck"           # Returns same value indefinitely
    DROPOUT = "dropout"       # Stops publishing
    DRIFT = "drift"           # Gradually shifts readings
    NOISE_SPIKE = "noise_spike"  # Occasional large outliers

def inject_failure(self, mode: FailureMode, duration_ticks: int):
    """Called by scenario scripts to simulate sensor failures."""
    self.failure_mode = mode
    self.failure_duration = duration_ticks
```

Failure modes create the interesting test cases. An agent that can distinguish
sensor drift from real conditions change is demonstrating real judgment.

### Sensor types

```python
class TemperatureSensor(SensorBase):
    sensor_type = "temperature"

    def _read_world(self, world_state) -> float:
        base = world_state.get_temperature(self.location)
        return base  # noise applied in base class

class HumiditySensor(SensorBase):
    sensor_type = "humidity"

    def _read_world(self, world_state) -> float:
        return world_state.get_humidity(self.location)

class WindSensor(SensorBase):
    sensor_type = "wind"

    def _read_world(self, world_state) -> dict:
        return {
            "speed_mph": world_state.get_wind_speed(self.location),
            "direction_deg": world_state.get_wind_direction(self.location)
        }

class SmokeSensor(SensorBase):
    sensor_type = "smoke"

    def _read_world(self, world_state) -> float:
        return world_state.get_smoke_density(self.location)
```

### Source data note

Start synthetic. Real data adds demo value but slows early development and removes
ground truth. NOAA RAWS and USGS fire perimeter data are freely available for future
integration. The sensor base class interface is identical either way — real data
is just another implementation of `_read_world`.

---

## Component 3: Canonical Event Schema

Every sensor reading on the wire has this structure. Typed strictly.
The NN integration (Phase 2) will need all of these fields — include them now.

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SensorEvent(BaseModel):
    # Identity
    event_id: str                    # UUID
    sensor_id: str                   # stable sensor identifier
    sensor_type: str                 # temperature | humidity | wind | smoke | camera
    cluster_id: str                  # geographic cluster

    # Time
    timestamp: datetime              # wall clock
    sim_tick: int                    # simulation tick for replay/debug

    # Reading
    value: float | dict              # sensor-specific
    confidence: float                # 0.0-1.0, set by sensor health

    # Context — include all of these now, NN will need them in Phase 2
    temperature_f: Optional[float]
    humidity_pct: Optional[float]
    wind_speed_mph: Optional[float]
    wind_direction_deg: Optional[float]
    fuel_moisture_pct: Optional[float]   # simulated — add now even if unused
    terrain_type: Optional[str]

    metadata: dict = {}


# Clean current conditions snapshot — critical for Phase 2 NN integration
class ConditionSnapshot(BaseModel):
    """Current conditions at a point in time. This is what the NN will receive."""
    timestamp: datetime
    sim_tick: int
    temperature_f: float
    humidity_pct: float
    wind_speed_mph: float
    wind_direction_deg: float
    fuel_moisture_pct: float
    terrain_type: str
    humidity_trend_1hr: float      # rate of change
    temp_trend_1hr: float          # rate of change
    cluster_id: str
```

**Design note:** `ConditionSnapshot` is the clean current-state field that feeds the
NN tool in Phase 2. Structuring it as a first-class type now means zero refactoring later.

---

## Component 4: Data Transport

Two buses, kept strictly separate.

| Bus | Direction | Contents |
|-----|-----------|----------|
| Sensor event bus | Sensors → Agents | Sensor readings, anomaly events |
| Command bus | Agents → Actuators | Structured actuator commands |
| Result bus | Actuators → Agents | Command outcomes, state changes |

### Topic design

```
sensors.raw.{cluster_id}     ← raw readings per cluster
events.anomaly               ← agent-detected anomalies
agents.decisions             ← agent decision log (full audit trail)
commands.actuators           ← agent → actuator commands
results.actuators            ← actuator outcomes
```

### Tool outputs — use structured dicts, not strings

This is the most important coding convention for Phase 2 compatibility.

```python
# WRONG — LLM has to parse prose, NN can't use this at all
return "Conditions are dangerous with temp 98F and humidity 8%"

# RIGHT — clean, typed, NN output slots in as another key later
return {
    "risk_level": "extreme",
    "temperature_f": 98.4,
    "humidity_pct": 8.2,
    "wind_speed_mph": 34.7,
    "contributing_factors": ["low_humidity", "high_wind"],
    "confidence": 0.91
}
```

---

## Component 5: Actuator Layer

Actuators receive structured commands from agents and apply consequences to world state.

### Base class

```python
class ActuatorBase(ABC):
    def __init__(self, actuator_id, world_state):
        self.actuator_id = actuator_id
        self.world_state = world_state
        self.command_log = []

    def receive_command(self, command: ActuatorCommand) -> ActuatorResult:
        validated = self._validate(command)
        if not validated.ok:
            return ActuatorResult(success=False, reason=validated.error)

        self.command_log.append(command)
        consequence = self._apply(command)
        self.world_state.apply(consequence)

        return ActuatorResult(
            success=True,
            actuator_id=self.actuator_id,
            command_id=command.command_id,
            consequence=consequence
        )

    @abstractmethod
    def _validate(self, command) -> ValidationResult:
        pass

    @abstractmethod
    def _apply(self, command) -> WorldStateChange:
        pass
```

### Actuator types

```python
class AlertDispatchActuator(ActuatorBase):
    """Sends alert notifications. Logs recipient, urgency, message."""

class DroneTaskingActuator(ActuatorBase):
    """Moves drone entity in world state. Changes sensor coverage of target sector."""

class HumanEscalationActuator(ActuatorBase):
    """Triggers interrupt() in Temporal workflow. Pauses for human approval."""

class ResourceDispatchActuator(ActuatorBase):
    """Updates resource registry. Marks unit as deployed. Updates travel time estimates."""
```

**Critical:** Actuator consequences write back to world state. This closes the loop.
A dispatched drone changes what sensors can observe. A deployed tanker changes available
resources. Without this feedback the simulation is open-loop and the demo is static.

---

## Component 6: Simulated GIS and Logistics

Completely simulated. No real GIS library needed. Full control over scenario drama.

### Travel time matrix

```python
# Lookup table — no routing math required
TRAVEL_MINUTES = {
    ("station_north", "A1"): 12,
    ("station_north", "B2"): 18,
    ("station_north", "C3"): 34,
    ("station_south", "C3"): 14,   # ← close, but tanker already deployed
    ("station_south", "B2"): 22,
    ("station_east",  "B2"): 28,
    ("station_east",  "C3"): 19,
}
```

### Resource registry

```python
RESOURCES = {
    "engine_12": {
        "type": "engine",
        "station": "station_north",
        "status": "available",
        "water_gallons": 500,
        "crew_count": 4,
        "fuel_pct": 0.82
    },
    "tanker_7": {
        "type": "air_tanker",
        "station": "station_south",
        "status": "deployed",          # ← already out — creates tension
        "retardant_gallons": 0,
        "eta_return_minutes": 22
    },
    "engine_9": {
        "type": "engine",
        "station": "station_east",
        "status": "available",
        "water_gallons": 500,
        "crew_count": 3,
        "fuel_pct": 0.61
    }
}
```

### The three levers that create scenario drama

1. **Population field** — fire approaching "suburban" triggers urgency audiences feel
2. **Travel time asymmetry** — nearest station's best unit is already deployed
3. **Resource margin** — engineer scenarios so margin is visible and agent decision changes outcome

The 12-minute margin in the demo scenario is deliberate. Resources are just barely
adequate if the agent acts promptly. This makes the recommendation feel consequential.

---

## Component 7: Agent Layer

### LangGraph state

```python
from typing import TypedDict, Annotated
from langgraph.graph import add_messages

class AgentState(TypedDict):
    # Message history for LLM context
    messages: Annotated[list, add_messages]

    # Raw sensor accumulation
    sensor_history: list[SensorEvent]

    # IMPORTANT: Clean current snapshot for Phase 2 NN tool
    current_conditions: ConditionSnapshot

    # Detected incidents being tracked
    incidents: list[Incident]

    # Current resource state
    resources: dict

    # Pending decisions awaiting human approval
    pending_approval: dict | None

    # Situation report (generated by supervisor)
    situation_report: str | None
```

### Tools — structured output pattern

All tools return typed dicts. Consistent contract. NN output will slot in as
additional keys without structural changes.

```python
from langchain_core.tools import tool

@tool
def get_sensor_readings(
    cluster_id: str,
    lookback_ticks: int = 10
) -> dict:
    """
    Returns recent sensor readings for a cluster.
    Includes current conditions snapshot and trends.
    """
    readings = sensor_store.get_recent(cluster_id, lookback_ticks)
    return {
        "cluster_id": cluster_id,
        "readings": readings,
        "current_conditions": build_snapshot(readings),
        "humidity_trend": calculate_trend(readings, "humidity"),
        "temp_trend": calculate_trend(readings, "temperature")
    }

@tool
def get_available_resources(
    sector: str,
    max_travel_minutes: int = 30
) -> dict:
    """
    Returns firefighting resources that can reach a sector within time limit.
    Includes current status, capacity, and travel time.
    """
    available = []
    for unit_id, unit in RESOURCES.items():
        if unit["status"] == "available":
            travel = TRAVEL_MINUTES.get((unit["station"], sector))
            if travel and travel <= max_travel_minutes:
                available.append({
                    "unit_id": unit_id,
                    "type": unit["type"],
                    "travel_minutes": travel,
                    "water_gallons": unit.get("water_gallons", 0),
                    "crew_count": unit.get("crew_count", 0)
                })
    return {
        "sector": sector,
        "max_travel_minutes": max_travel_minutes,
        "available_units": available,
        "total_water_gallons": sum(u["water_gallons"] for u in available),
        "sufficient": len(available) >= 2   # simple heuristic
    }

@tool
def dispatch_unit(
    unit_id: str,
    destination_sector: str,
    priority: str
) -> dict:
    """
    Dispatches a unit to a sector. Updates resource registry.
    Returns confirmation and updated resource state.
    """
    if RESOURCES[unit_id]["status"] != "available":
        return {"success": False, "reason": f"{unit_id} is not available"}

    RESOURCES[unit_id]["status"] = "deployed"
    RESOURCES[unit_id]["destination"] = destination_sector

    return {
        "success": True,
        "unit_id": unit_id,
        "destination": destination_sector,
        "travel_minutes": TRAVEL_MINUTES[(RESOURCES[unit_id]["station"], destination_sector)],
        "priority": priority
    }

@tool
def assess_resource_sufficiency(
    sector: str,
    fire_intensity: str,
    spread_direction: str
) -> dict:
    """
    Assesses whether available resources are adequate for current conditions.
    Considers fire intensity, spread direction, and available units.
    """
    available = get_available_resources(sector, max_travel_minutes=30)
    return {
        "sector": sector,
        "fire_intensity": fire_intensity,
        "available_resources": available,
        "assessment": "adequate" if available["sufficient"] else "insufficient",
        "recommendation": "pre-position now" if fire_intensity in ["high", "extreme"] else "monitor"
    }
```

### Cluster agent subgraph

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

cluster_tools = [
    get_sensor_readings,
    assess_resource_sufficiency,
]

def cluster_agent_node(state: AgentState):
    """LLM reasoning node for a geographic cluster."""
    response = llm.bind_tools(cluster_tools).invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: AgentState):
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return "supervisor"

cluster_graph = StateGraph(AgentState)
cluster_graph.add_node("agent", cluster_agent_node)
cluster_graph.add_node("tools", ToolNode(cluster_tools))
cluster_graph.add_edge("tools", "agent")
cluster_graph.add_conditional_edges("agent", should_continue)
cluster_graph.set_entry_point("agent")

cluster_subgraph = cluster_graph.compile(checkpointer=postgres_checkpointer)
```

### Supervisor agent with Send API fan-out

```python
from langgraph.types import Send

def dispatch_to_clusters(state: SupervisorState):
    """Fan out to all active cluster agents in parallel."""
    return [
        Send("cluster_agent", {
            "cluster_id": cluster_id,
            "messages": build_cluster_context(state, cluster_id)
        })
        for cluster_id in state["active_clusters"]
    ]

supervisor_graph = StateGraph(SupervisorState)
supervisor_graph.add_node("cluster_agent", cluster_subgraph)
supervisor_graph.add_node("synthesize", synthesize_findings)
supervisor_graph.add_node("decide", make_decision)
supervisor_graph.add_conditional_edges(
    START,
    dispatch_to_clusters,
    ["cluster_agent"]
)
supervisor_graph.add_edge("cluster_agent", "synthesize")
supervisor_graph.add_edge("synthesize", "decide")
```

### Human-in-the-loop with interrupt()

```python
from langgraph.types import interrupt

def escalation_node(state: AgentState):
    """
    Pauses for human approval before firing actuators.
    Temporal keeps the workflow alive indefinitely.
    Human approves → execution resumes from this point.
    """
    decision = state["pending_approval"]

    # This suspends the graph. Temporal holds state.
    # Resume by invoking with same thread_id + human_input.
    human_input = interrupt({
        "message": "Agent recommends the following action. Approve?",
        "recommendation": decision,
        "situation_report": state["situation_report"],
        "resources_to_deploy": decision["units"],
        "estimated_margin_minutes": decision["margin_minutes"]
    })

    if human_input["approved"]:
        return {"pending_approval": None, "approved_action": decision}
    else:
        return {"pending_approval": None, "approved_action": None,
                "override_reason": human_input.get("reason")}
```

---

## Component 8: Kafka ↔ Temporal Integration

### The three rules

1. `enable.auto.commit=false` — manual offset control
2. Call Temporal, wait for ACK, then commit offset
3. Use `{topic}:{partition}:{offset}` as workflow ID — natural dedup key

When Kafka re-delivers and the bridge calls `start_workflow()` again with the same ID,
Temporal returns "already exists" — no duplicate work, no special handling needed.

### Bridge consumer

```python
from temporalio.client import Client, WorkflowAlreadyStartedError
from confluent_kafka import Consumer, KafkaException

async def run_bridge_consumer():
    temporal_client = await Client.connect("localhost:7233")

    consumer = Consumer({
        "bootstrap.servers": "localhost:9092",
        "group.id": "temporal-bridge",
        "enable.auto.commit": False,          # Rule 1
        "auto.offset.reset": "earliest"
    })
    consumer.subscribe(["sensors.raw.cluster_a", "sensors.raw.cluster_b"])

    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue

        # Natural dedup key — Rule 3
        workflow_id = f"{msg.topic()}:{msg.partition()}:{msg.offset()}"

        event = SensorEvent.model_validate_json(msg.value())

        try:
            await temporal_client.start_workflow(
                ClusterAgentWorkflow.run,
                event,
                id=workflow_id,
                task_queue="agent-queue",
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY
            )
        except WorkflowAlreadyStartedError:
            pass  # Idempotent — already running, nothing to do

        # Commit only after Temporal ACK — Rule 2
        consumer.commit(msg)
```

### Temporal workflow wrapping LangGraph

```python
from temporalio import workflow, activity
from temporalio.common import RetryPolicy
from datetime import timedelta

@activity.defn
async def run_cluster_agent(event: SensorEvent) -> AgentDecision:
    """LangGraph subgraph invocation lives here — in an Activity, not a Workflow."""
    result = await cluster_subgraph.ainvoke(
        {"messages": [build_initial_message(event)],
         "current_conditions": build_snapshot(event)},
        config={"configurable": {"thread_id": event.sensor_id}}
    )
    return extract_decision(result)

@workflow.defn
class ClusterAgentWorkflow:
    @workflow.run
    async def run(self, event: SensorEvent) -> AgentDecision:
        return await workflow.execute_activity(
            run_cluster_agent,
            event,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                backoff_coefficient=2.0
            )
        )
```

**Key principle:** Temporal workflow code must be deterministic. All LLM calls,
database queries, and sensor reads go inside Activities, not Workflows.

---

## The Demo Scenario

```
T=0    Conditions nominal. All sensors green. Resources at station.

T=15   Temp spike in cluster B. Humidity beginning to drop.
       Cluster agent flags: elevated risk. Confidence: moderate.

T=25   Wind shift detected. Humidity drop accelerating (-4pts/15min).
       Cluster agent escalates to supervisor.
       Supervisor: cross-cluster correlation confirms pattern is real.

T=30   Ignition detected in sector B2.
       Tool call: get_available_resources(sector="C3", max_travel=30)
       Result: engine_12 (18min), engine_9 (19min). tanker_7 unavailable.
       Tool call: assess_resource_sufficiency(sector="C3", intensity="high")
       Result: adequate IF dispatched now. Margin: ~12 minutes.

T=32   Supervisor generates recommendation:
       "Pre-position engine_12 and engine_9 to C3 staging area.
        Request tanker_7 return to base. Margin is 12 minutes —
        do not wait for further confirmation."

       → interrupt() fires
       → Human approval requested

T=34   Human approves pre-positioning.
       dispatch_unit("engine_12", "C3", priority="high")
       dispatch_unit("engine_9", "C3", priority="high")
       Resource registry updates. Units en route.

T=45   Fire reaches B3. Spreading toward C3.
       Units arrive at staging area. Margin used: 11 minutes.

T=50   Supervisor generates situation report:
       "Pre-positioning decision provided 11-minute advantage.
        Current resources adequate for initial attack on C3.
        Recommend mutual aid request if fire exceeds 50 acres.
        Tanker_7 ETA: 22 minutes."
```

This scenario demonstrates in a single run:
- Multi-sensor correlation
- Dynamic resource lookup via tools
- Structured output from agent to actuator
- interrupt() with real stakes
- Human-in-the-loop approval
- Situation report generation
- Feedback loop — resource dispatch changes world state

---

## LangGraph Skills Coverage

### 1. Graph Primitives

| Skill | Level | Testbed coverage | Where |
|-------|-------|-----------------|-------|
| StateGraph + TypedDict state | foundational | covered | Every subgraph |
| Nodes — functions vs runnables | foundational | covered | All agent nodes |
| Edges — normal vs conditional | foundational | covered | Post-classification routing |
| Reducers and Annotated state | mid-level | covered | Merging parallel sensor nodes |
| Compile + invoke / stream | foundational | covered | All graph entry points |

### 2. Control Flow

| Skill | Level | Testbed coverage | Where |
|-------|-------|-----------------|-------|
| Cycles / loops | mid-level | covered | Agent retries ambiguous reading |
| Parallel node execution (Send API) | mid-level | covered | Supervisor fans out to N clusters |
| Dynamic branching | mid-level | covered | Route to wildfire / fault / weather branch |
| Recursion limit + error handling | advanced | partial | Needs runaway loop scenario |

### 3. Tools

| Skill | Level | Testbed coverage | Where |
|-------|-------|-----------------|-------|
| Tool definition — @tool decorator | foundational | covered | All sensor + logistics tools |
| ToolNode + bind_tools | foundational | covered | Cluster agent tool loop |
| Tool errors + fallback | mid-level | partial | Sensor timeout scenario |
| Structured output tools | mid-level | covered | ActuatorCommand schema |

### 4. Memory and Persistence

| Skill | Level | Testbed coverage | Where |
|-------|-------|-----------------|-------|
| Checkpointers — MemorySaver vs PostgresSaver | mid-level | covered | All persistent agents |
| Thread-level vs cross-thread memory | mid-level | covered | Supervisor shares via Store |
| Long-term memory with Store + embeddings | advanced | partial | Past incident recall |
| State schema evolution | advanced | not yet | Separate exercise |

### 5. Multi-Agent

| Skill | Level | Testbed coverage | Where |
|-------|-------|-----------------|-------|
| Subgraphs — compile and invoke | mid-level | covered | Each cluster agent |
| State schema handoff between graphs | mid-level | covered | Supervisor → ClusterAgentState |
| Supervisor pattern | mid-level | covered | Core of the testbed |
| Agent handoff / swarm pattern | advanced | partial | Needs explicit scenario |

### 6. Human-in-the-Loop

| Skill | Level | Testbed coverage | Where |
|-------|-------|-----------------|-------|
| interrupt() — pause and resume | mid-level | covered | High-confidence alert approval |
| State editing before resume | advanced | partial | Human overrides classification |
| Time travel / replay | advanced | not yet | High value to add as scenario |

**Note on time travel:** `get_state_history()` + re-invoke from past checkpoint.
"Here's the incident — let me rewind 10 minutes and try a different response."
This is a scenario addition, not an architecture change. Very high demo value.

### 7. Streaming and Observability

| Skill | Level | Testbed coverage | Where |
|-------|-------|-----------------|-------|
| stream_mode — values / updates / debug | mid-level | covered | Live dashboard |
| LangSmith tracing | mid-level | covered | Always on |
| Custom callbacks | advanced | partial | Emit Kafka events from decisions |

---

## Phase 2: Neural Net Integration

**Do not build this until the agentic system is complete.**
Everything in this section is design prep — decisions to make now that cost nothing
but prevent painful refactoring later.

### Why a NN adds value here

The LLM can say "conditions favor rapid spread." It cannot say "estimated 340 acres/hour."
That number requires a statistical model trained on historical data. With it, the agent can say:
"At 340 acres/hour we have approximately 18 minutes before sector C3 is threatened."
Neither component alone produces that sentence.

### What to train it on

Real RAWS (Remote Automated Weather Station) historical data. Freely available from USFS
and NIFC. These are physical sensor readings from real fire-prone stations — exactly the
input your simulated sensors are mimicking.

### What to predict

**Spread rate (acres/hour)** is the highest-value target. It's a regression problem,
not classification. It's what the LLM genuinely can't compute. It feeds directly into
the logistics margin calculation.

### The minimal model

```python
# Features — all present in ConditionSnapshot (which you're already building)
X = df[[
    'temperature_f',
    'humidity_pct',
    'wind_speed_mph',
    'wind_direction_deg',
    'fuel_moisture_pct',
    'slope_pct'
]]

# Target
y = df['spread_rate_acres_per_hour']

# Model — this is enough
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

model = MLPRegressor(
    hidden_layer_sizes=(64, 32),
    max_iter=500,
    random_state=42
)
model.fit(X_train_scaled, y_train)

# Serialize for demo
import joblib
joblib.dump(model, "models/spread_rate_model.pkl")
joblib.dump(scaler, "models/spread_rate_scaler.pkl")
```

**Do not over-engineer features.** Normalization is the only preprocessing step needed.
The network finds the relationships. Pre-computing "danger indices" bakes in your
assumptions and usually makes it worse.

### The LangGraph tool

```python
@tool
def predict_spread_rate(
    temperature_f: float,
    humidity_pct: float,
    wind_speed_mph: float,
    wind_direction_deg: float,
    fuel_moisture_pct: float,
    terrain_type: str
) -> dict:
    """
    Predicts fire spread rate using trained neural network.
    Returns acres/hour estimate with confidence indicator.
    Use this when assessing how quickly a fire may grow.
    """
    features = scaler.transform([[
        temperature_f,
        humidity_pct,
        wind_speed_mph,
        wind_direction_deg,
        fuel_moisture_pct,
        TERRAIN_SLOPE[terrain_type]
    ]])

    prediction = model.predict(features)[0]

    return {
        "spread_rate_acres_per_hour": round(float(prediction), 1),
        "confidence": "high",
        "model": "neural_net_v1",
        "inputs_used": {
            "temperature_f": temperature_f,
            "humidity_pct": humidity_pct,
            "wind_speed_mph": wind_speed_mph
        }
    }
```

This tool slots into the existing tool list with zero structural changes to the agent.
The LLM calls it exactly like any other tool.

### What to do now to make Phase 2 easy

Three things. All cheap. All in the current build.

**1. Typed tool outputs (not strings)**
Already covered in Component 4. The NN output is just another key in the dict.

**2. Complete sensor schema**
`ConditionSnapshot` already includes `fuel_moisture_pct` and `terrain_type`.
These are simulated values — add them now even though nothing uses them yet.

**3. `current_conditions` as a first-class state field**
Already in `AgentState` as `ConditionSnapshot`. This is exactly what gets passed to
the NN tool. No preprocessing step at integration time.

### LLM-as-data-synthesizer option

If you want training data before you have clean historical labels:

```
Prompt Claude:
"Generate 500 realistic wildfire sensor reading scenarios as JSON.
 For each, include: temperature_f, humidity_pct, wind_speed_mph,
 wind_direction_deg, fuel_moisture_pct, terrain_slope_pct,
 and spread_rate_acres_per_hour based on established fire behavior principles.
 Cover the full range from benign to extreme conditions."
```

Validate outputs against published Red Flag criteria (known thresholds).
Use as bootstrap training data. Replace with real RAWS data when available.

### The combined demo narrative

| Component | Contribution | Audience sees |
|-----------|-------------|---------------|
| Sensor simulation | Deteriorating conditions | Numbers changing |
| LLM classifier | "Red flag conditions" | Plain English reasoning |
| NN spread predictor | "340 acres/hour" | A specific confident number |
| LLM logistics reasoner | "18 minutes — act now" | Decision with stakes |
| interrupt() | Pause for approval | Human in the loop |
| Actuator | Resources dispatched | Something visibly happens |

Every component does what it is actually good at. Nothing pretends.

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Event bus | Kafka | Sensor events, commands, results |
| Durable execution | Temporal | Crash recovery, HITL, workflow history |
| Agent framework | LangGraph | Subgraphs, state, tool loops |
| LLM | Anthropic Claude | Classification, correlation, planning |
| Persistence | Postgres | Temporal backend + LangGraph checkpointer |
| Vector memory | pgvector | Semantic incident recall (Phase 2) |
| Observability | LangSmith + Temporal UI | Agent traces + workflow history |
| ML (Phase 2) | sklearn MLPRegressor | Spread rate prediction |
| Language | Python | Temporal Python SDK + LangGraph |

---

## Recommended Build Order

Follow this order — each step exercises the next level of LangGraph capability.

| Step | Component | LangGraph skill unlocked |
|------|-----------|------------------------|
| 1 | World engine — tick, entities, fire spread | Python fundamentals |
| 2 | Sensor base class + 2-3 sensor types | — |
| 3 | Kafka topics + canonical event schema | — |
| 4 | Single cluster agent with ToolNode loop | Graph primitives, tools |
| 5 | Temporal worker hosting cluster agent | Activity pattern |
| 6 | Bridge consumer (Kafka → Temporal + dedup) | Integration pattern |
| 7 | Actuator base class + alert dispatch | Structured output tools |
| 8 | Supervisor with Send API fan-out | Parallel execution |
| 9 | Postgres checkpointer + crash scenario | Persistence |
| 10 | interrupt() — alert requiring human approval | Human-in-the-loop |
| 11 | Cross-agent Store for shared incident history | Cross-thread memory |
| 12 | LangSmith tracing throughout | Observability |
| 13 | Scenario scripts — sensor fault, real fire | Scenario design |
| 14 | Logistics tools + resource registry | Multi-tool reasoning |
| 15 | Full demo scenario end-to-end | All of the above |
| 16 | pgvector past incident recall | Long-term memory |
| 17 | Time travel scenario | Advanced HITL |
| 18 | NN spread rate model (Phase 2) | Hybrid architecture |

---

*Design document compiled from architecture conversation.*
*Intended as context for Claude Code implementation.*
*Last updated: April 2026*