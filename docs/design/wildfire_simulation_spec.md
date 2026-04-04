# Wildfire Simulation System — Claude Opus Design & Build Prompt

## Goal
Design and implement a modular wildfire simulation system that enables an AI agent to make operational decisions based on simulated environmental, fire, and logistics data.

---

## Core Principles

- **Modularity first**: All major components must be swappable.
- **Physics is abstracted**: Fire behavior is a placeholder behind an interface.
- **Synthetic but realistic**: GIS and logistics are simulated but must follow real-world constraints.
- **Agent-focused design**: The system exists to test reasoning and decision-making, not physical accuracy.

---

## System Components

### 1. Sensors
Simulated environmental inputs:
- Temperature (°C)
- Humidity (%)
- Wind (speed + direction)
- Optional: smoke, pressure, soil moisture

**Requirements:**
- Correlated where appropriate (e.g., high temp → lower humidity)
- JSON output format
- Timestamped
- Reference to real-world data schema (optional)

---

### 2. World Engine
Central simulation engine.

**Responsibilities:**
- Maintain world state over time
- Accept sensor inputs
- Apply fire spread logic
- Produce predicted fire state

**Key Requirement:**
- Fire spread must be implemented via a pluggable interface

---

### 3. FireSpreadModule (Interface)

Defines contract for fire behavior.

**Input:**
- World state (sensor data, current fire cells)

**Output:**
- Updated fire cells
- Spread rate
- Predicted fire path
- Intensity map (optional)

**Implementations:**
- FireSpreadHeuristic (placeholder)
- Future: physics-based or ML-based model

---

### 4. Logistics Simulation

Synthetic but structured representation of:

- Fire trucks (location, ETA, capacity)
- Crews / hotshots
- Aircraft (range, payload)
- Water sources (pressure, flow rate)

**Requirements:**
- Must support resource allocation decisions
- No real GIS required — use grid or abstract locations

---

### 5. Agent Layer

Consumes:
- Current world state
- Historical data (optional)

Produces:
- Resource allocation decisions
- Firebreak recommendations
- Risk assessments

---

## Data Flow

[Sensor Streams] → [Collector / Staging] → [World Engine] → [Agent]

---

## Data Formats (Examples)

### Sensor Reading
```json
{
  "sensor": "temperature_1",
  "value": 32.5,
  "unit": "C",
  "timestamp": "2026-04-01T14:33:00Z"
}
```

### World State
```json
{
  "time": "2026-04-01T14:33:00Z",
  "sensor_readings": [...],
  "fire_cells": ["cell_1", "cell_2"],
  "predicted_path": [...],
  "anomaly": null
}
```

---

## Design Requirements

1. Clearly separate **interfaces vs implementations**
2. Label all placeholder logic explicitly
3. Ensure all modules are independently replaceable
4. Keep the system simple but extensible
5. Avoid overengineering physics or GIS

---

## Task for Claude Opus

1. Design the full module structure
2. Define all interfaces clearly
3. Implement a Python scaffold
4. Include:
   - WorldEngine
   - FireSpreadModule interface
   - Placeholder FireSpreadHeuristic
   - Basic sensor simulation
   - Basic logistics structures
5. Ensure clean, professional, extensible code

---

## Important Notes

- Do NOT attempt real wildfire physics
- Do NOT depend on real GIS data
- Focus on architecture and clarity
- This is a simulation for testing AI reasoning, not prediction accuracy
