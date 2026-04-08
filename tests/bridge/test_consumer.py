"""Tests for ogar.bridge.consumer — EventBridgeConsumer."""

import asyncio

import pytest

from bridge.consumer import EventBridgeConsumer
from transport import SensorEventQueue, SensorEvent


def _make_event(source_id: str = "s1", cluster_id: str = "cluster-north") -> SensorEvent:
    return SensorEvent.create(
        source_id=source_id,
        source_type="temperature",
        cluster_id=cluster_id,
        payload={"celsius": 42.0},
    )


@pytest.fixture
def queue():
    return SensorEventQueue(maxsize=100)


class TestEventBridgeConsumer:
    @pytest.mark.asyncio
    async def test_consume_single_event(self, queue):
        await queue.put(_make_event())
        consumer = EventBridgeConsumer(queue=queue)
        await consumer.run(max_events=1)
        assert consumer.events_consumed == 1
        assert "cluster-north" in consumer.events_by_cluster
        assert len(consumer.events_by_cluster["cluster-north"]) == 1

    @pytest.mark.asyncio
    async def test_groups_events_by_cluster(self, queue):
        for i in range(5):
            await queue.put(_make_event(f"s{i}"))
        consumer = EventBridgeConsumer(queue=queue)
        await consumer.run(max_events=5)
        assert consumer.events_consumed == 5
        assert len(consumer.events_by_cluster["cluster-north"]) == 5

    @pytest.mark.asyncio
    async def test_multiple_clusters(self, queue):
        await queue.put(_make_event("s1", cluster_id="cluster-north"))
        await queue.put(_make_event("s2", cluster_id="cluster-south"))
        consumer = EventBridgeConsumer(queue=queue)
        await consumer.run(max_events=2)
        assert consumer.events_consumed == 2
        assert "cluster-north" in consumer.events_by_cluster
        assert "cluster-south" in consumer.events_by_cluster
        assert len(consumer.events_by_cluster["cluster-north"]) == 1
        assert len(consumer.events_by_cluster["cluster-south"]) == 1

    @pytest.mark.asyncio
    async def test_stop_terminates(self, queue):
        consumer = EventBridgeConsumer(queue=queue)

        async def stop_soon():
            await asyncio.sleep(0.1)
            consumer.stop()

        asyncio.create_task(stop_soon())
        await consumer.run()
        # Should return without hanging.

    @pytest.mark.asyncio
    async def test_empty_queue_stop(self, queue):
        consumer = EventBridgeConsumer(queue=queue)
        await consumer.run(max_events=0)
        assert consumer.events_consumed == 0
        assert consumer.events_by_cluster == {}

    @pytest.mark.asyncio
    async def test_events_preserve_order(self, queue):
        for i in range(4):
            await queue.put(_make_event(f"s{i}"))
        consumer = EventBridgeConsumer(queue=queue)
        await consumer.run(max_events=4)
        events = consumer.events_by_cluster["cluster-north"]
        source_ids = [e.source_id for e in events]
        assert source_ids == ["s0", "s1", "s2", "s3"]


class TestPublisherEngineTick:
    """Tests that SensorPublisher advances WorldEngine when wired."""

    @pytest.mark.asyncio
    async def test_publisher_ticks_engine(self):
        from sensors import SensorPublisher
        from sensors.base import SensorBase
        from domains.wildfire import FirePhysicsModule
        from domains.wildfire.environment import FireEnvironmentState
        from world import GenericWorldEngine
        from world.generic_grid import GenericTerrainGrid

        physics = FirePhysicsModule(base_probability=0.0)
        grid = GenericTerrainGrid(rows=3, cols=3, initial_state_factory=physics.initial_cell_state)
        env = FireEnvironmentState(temp_drift=0.0, humidity_drift=0.0,
                                   wind_speed_drift=0.0, wind_direction_drift=0.0,
                                   pressure_drift=0.0)
        engine = GenericWorldEngine(grid=grid, environment=env, physics=physics)

        class _Stub(SensorBase):
            source_type = "stub"
            def read(self, local_conditions=None):
                return {"v": 1}

        q = SensorEventQueue()
        sensor = _Stub(source_id="s1", cluster_id="c1")
        pub = SensorPublisher(
            sensors=[sensor], queue=q, tick_interval_seconds=0.0, engine=engine,
        )

        assert engine.current_tick == 0
        await pub.run(ticks=5)
        assert engine.current_tick == 5
        assert q.total_enqueued == 5

    @pytest.mark.asyncio
    async def test_publisher_without_engine_unchanged(self):
        from sensors import SensorPublisher
        from sensors.base import SensorBase

        class _Stub(SensorBase):
            source_type = "stub"
            def read(self, local_conditions=None):
                return {"v": 1}

        q = SensorEventQueue()
        sensor = _Stub(source_id="s1", cluster_id="c1")
        pub = SensorPublisher(
            sensors=[sensor], queue=q, tick_interval_seconds=0.0,
        )

        await pub.run(ticks=3)
        assert q.total_enqueued == 3
