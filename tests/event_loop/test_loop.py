"""Tests for event_loop.loop — EventLoop orchestration."""

import asyncio
import pytest

from event_loop.loop import EventLoop, EventLoopConfig
from event_loop.sensor_filter import SensorFilter
from event_loop.sensor_generator import SensorGenerator
from event_loop.store import InMemoryLocationStore


# ── Test doubles ──────────────────────────────────────────────────────────────

class AlwaysTriggerFilter(SensorFilter):
    """Filter that always triggers — for testing batch delivery."""
    def should_trigger(self, recent_events):
        return True, "always triggers"


class NeverTriggerFilter(SensorFilter):
    """Filter that never triggers."""
    def should_trigger(self, recent_events):
        return False, "never triggers"


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestEventLoopSimulation:
    def _make_config(self, cycles: int = 3, locations=None) -> EventLoopConfig:
        return EventLoopConfig(
            location_ids=locations or ["loc-A", "loc-B"],
            cycle_speed_seconds=0.0,
            simulation_cycles=cycles,
            mode="SIMULATION",
        )

    @pytest.mark.asyncio
    async def test_runs_for_configured_cycles(self):
        config = self._make_config(cycles=5)
        loop = EventLoop(config, sensor_filter=NeverTriggerFilter())
        await loop.run()
        assert loop.cycles_completed == 5

    @pytest.mark.asyncio
    async def test_store_populated_after_run(self):
        store = InMemoryLocationStore()
        config = self._make_config(cycles=3, locations=["loc-A", "loc-B"])
        loop = EventLoop(config, store=store, sensor_filter=NeverTriggerFilter())
        await loop.run()
        assert store.get("loc-A") is not None
        assert store.get("loc-B") is not None

    @pytest.mark.asyncio
    async def test_on_batch_called_when_triggered(self):
        batches = []
        config = self._make_config(cycles=3)
        loop = EventLoop(
            config,
            sensor_filter=AlwaysTriggerFilter(),
            on_batch=batches.append,
        )
        await loop.run()
        assert len(batches) == 3  # one batch per cycle (all locations trigger)

    @pytest.mark.asyncio
    async def test_on_batch_not_called_when_no_trigger(self):
        batches = []
        config = self._make_config(cycles=5)
        loop = EventLoop(
            config,
            sensor_filter=NeverTriggerFilter(),
            on_batch=batches.append,
        )
        await loop.run()
        assert len(batches) == 0

    @pytest.mark.asyncio
    async def test_batch_shape(self):
        batches = []
        config = self._make_config(cycles=1, locations=["loc-A", "loc-B"])
        loop = EventLoop(
            config,
            sensor_filter=AlwaysTriggerFilter(),
            on_batch=batches.append,
        )
        await loop.run()
        assert len(batches) == 1
        batch = batches[0]
        assert "active_cluster_ids" in batch
        assert "events_by_cluster" in batch
        assert set(batch["active_cluster_ids"]) == {"loc-A", "loc-B"}
        assert "loc-A" in batch["events_by_cluster"]
        assert "loc-B" in batch["events_by_cluster"]

    @pytest.mark.asyncio
    async def test_batch_events_are_lists_of_dicts(self):
        batches = []
        config = self._make_config(cycles=2, locations=["loc-A"])
        loop = EventLoop(
            config,
            sensor_filter=AlwaysTriggerFilter(),
            on_batch=batches.append,
        )
        await loop.run()
        last_batch = batches[-1]
        events = last_batch["events_by_cluster"]["loc-A"]
        assert isinstance(events, list)
        assert len(events) >= 1
        assert "temperature_c" in events[0]
        assert "location_id" in events[0]

    @pytest.mark.asyncio
    async def test_history_accumulates_across_cycles(self):
        store = InMemoryLocationStore()
        config = self._make_config(cycles=5, locations=["loc-A"])
        loop = EventLoop(config, store=store, sensor_filter=NeverTriggerFilter())
        await loop.run()
        history = store.get_recent_events("loc-A")
        assert len(history) == 5  # one reading per cycle


class TestEventLoopKafkaStub:
    @pytest.mark.asyncio
    async def test_kafka_mode_raises(self):
        config = EventLoopConfig(
            location_ids=["loc-A"],
            mode="KAFKA",
            simulation_cycles=1,
        )
        loop = EventLoop(config)
        with pytest.raises(NotImplementedError):
            await loop.run()
