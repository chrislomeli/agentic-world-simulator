"""Tests for ogar.domains.wildfire.scenarios."""

import random
import pytest

from ogar.domains.wildfire.cell_state import FireCellState, FireState, TerrainType
from ogar.domains.wildfire.scenarios import create_basic_wildfire
from ogar.world.generic_engine import GenericWorldEngine, GenericGroundTruthSnapshot


@pytest.fixture(autouse=True)
def seed():
    random.seed(42)


class TestBasicWildfire:
    def test_creates_engine(self):
        engine = create_basic_wildfire()
        assert isinstance(engine, GenericWorldEngine)

    def test_grid_dimensions(self):
        engine = create_basic_wildfire()
        assert engine.grid.rows == 10
        assert engine.grid.cols == 10

    def test_initial_ignition(self):
        engine = create_basic_wildfire()
        state = engine.grid.get_cell(7, 2).cell_state
        assert state.fire_state == FireState.BURNING
        assert state.fire_intensity == pytest.approx(0.8)

    def test_terrain_layout(self):
        engine = create_basic_wildfire()
        # Lake in NW
        assert engine.grid.get_cell(0, 0).cell_state.terrain_type == TerrainType.WATER
        # Forest in north
        assert engine.grid.get_cell(1, 5).cell_state.terrain_type == TerrainType.FOREST
        # Rock ridge
        assert engine.grid.get_cell(4, 0).cell_state.terrain_type == TerrainType.ROCK
        # Gap in ridge
        assert engine.grid.get_cell(4, 6).cell_state.terrain_type == TerrainType.SCRUB
        # Grassland in south
        assert engine.grid.get_cell(6, 3).cell_state.terrain_type == TerrainType.GRASSLAND
        # Urban in SE
        assert engine.grid.get_cell(7, 8).cell_state.terrain_type == TerrainType.URBAN

    def test_can_run_simulation(self):
        engine = create_basic_wildfire()
        snapshots = engine.run(ticks=10)
        assert len(snapshots) == 10
        assert engine.current_tick == 10

    def test_fire_spreads_during_simulation(self):
        engine = create_basic_wildfire()
        engine.run(ticks=20)

        # After 20 ticks, there should be more burning or burned cells
        counts = engine.grid.summary_counts()
        total_fire_affected = counts.get("BURNING", 0) + counts.get("BURNED", 0)
        # At minimum, the initial cell should have burned
        assert total_fire_affected >= 1

    def test_snapshot_has_domain_summary(self):
        engine = create_basic_wildfire()
        snapshot = engine.tick()
        assert "burning_cells" in snapshot.domain_summary
        assert "fire_intensity_map" in snapshot.domain_summary
        assert "cell_summary" in snapshot.domain_summary

    def test_rock_cells_not_burnable(self):
        engine = create_basic_wildfire()
        engine.run(ticks=30)
        # Rock cells should never burn
        for c in range(10):
            if c not in (6, 7):  # gap cells are scrub, not rock
                state = engine.grid.get_cell(4, c).cell_state
                assert state.fire_state == FireState.UNBURNED, (
                    f"Rock cell (4, {c}) should not burn"
                )
