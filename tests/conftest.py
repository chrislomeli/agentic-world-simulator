"""
Shared fixtures for all ogar tests.

Seeding random ensures deterministic results across all test modules.
"""

import random
import pytest

from ogar.domains.wildfire.cell_state import FireCellState, FireState, TerrainType
from ogar.domains.wildfire.environment import FireEnvironmentState
from ogar.domains.wildfire.physics import FirePhysicsModule
from ogar.world.generic_engine import GenericWorldEngine
from ogar.world.generic_grid import GenericTerrainGrid
from ogar.transport.schemas import SensorEvent


@pytest.fixture(autouse=True)
def seed_random():
    """Seed RNG before every test for determinism."""
    random.seed(42)
    yield


@pytest.fixture
def fire_physics() -> FirePhysicsModule:
    return FirePhysicsModule(base_probability=0.15, burn_duration_ticks=5)


@pytest.fixture
def small_grid(fire_physics) -> GenericTerrainGrid:
    """A 5x5 grassland grid using FireCellState."""
    return GenericTerrainGrid(rows=5, cols=5, initial_state_factory=fire_physics.initial_cell_state)


@pytest.fixture
def fire_environment() -> FireEnvironmentState:
    """Hot, dry, windy weather — ideal for fire spread tests."""
    return FireEnvironmentState(
        temperature_c=38.0,
        humidity_pct=12.0,
        wind_speed_mps=8.0,
        wind_direction_deg=225.0,
        pressure_hpa=1008.0,
    )


@pytest.fixture
def engine(small_grid, fire_environment, fire_physics) -> GenericWorldEngine:
    """A GenericWorldEngine with a 5x5 grid, hot/dry weather, and fire physics."""
    return GenericWorldEngine(grid=small_grid, environment=fire_environment, physics=fire_physics)


@pytest.fixture
def sample_event() -> SensorEvent:
    """A pre-built SensorEvent for transport/agent tests."""
    return SensorEvent.create(
        source_id="temp-A1",
        source_type="temperature",
        cluster_id="cluster-north",
        payload={"celsius": 42.1},
        confidence=0.95,
    )
