"""
event_loop.store

Location state store abstraction.

Each location has exactly one current state — the latest sensor reading.
History is kept as a sliding window for trend detection by the sensor filter.

In production this would be Redis (or similar) so that:
  - Multiple event loop processes can share state
  - State survives restarts
  - History queries are fast

For the tutorial, InMemoryLocationStore provides an identical interface
backed by plain dicts and deques.  Swapping to Redis requires only changing
which concrete class you pass to EventLoop — consuming code is unchanged.

State record shape
──────────────────
{
    "location_id": "loc-A",
    "temperature_c": 28.0,       # Celsius
    "humidity_pct": 35.0,        # percent
    "wind_speed_mps": 5.0,       # m/s
    "wind_direction_deg": 180.0, # degrees
    "fuel_moisture_pct": 15.0,   # percent (oven-dry basis)
    "slope_deg": 10.0,           # terrain slope in degrees
    "timestamp": "2024-01-01T00:00:00Z"
}
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import deque

logger = logging.getLogger(__name__)


class LocationStateStore(ABC):
    """
    Abstract interface for location state storage.

    Concrete implementations: InMemoryLocationStore, RedisLocationStore.
    Pass an instance to EventLoop at construction time.
    """

    @abstractmethod
    def get(self, location_id: str) -> dict | None:
        """Return the current state for a location, or None if unknown."""

    @abstractmethod
    def set(self, location_id: str, state: dict) -> None:
        """Overwrite the current state for a location and append to history."""

    @abstractmethod
    def get_recent_events(self, location_id: str, n: int = 10) -> list[dict]:
        """
        Return the last N state records for a location, oldest first.

        Used by the sensor filter to detect trends across recent readings.
        Returns an empty list if the location is unknown.
        """

    @abstractmethod
    def get_all_location_ids(self) -> list[str]:
        """Return all location IDs that have ever been written to."""


# ── In-memory implementation ──────────────────────────────────────────────────

class InMemoryLocationStore(LocationStateStore):
    """
    In-process store backed by dicts and deques.

    Suitable for single-process demos and tests.
    Replace with RedisLocationStore for multi-process or persistent deployments.

    Parameters
    ──────────
    history_size : Maximum number of historical records kept per location.
                   Older records are discarded as new ones arrive.
    """

    def __init__(self, *, history_size: int = 20) -> None:
        self._current: dict[str, dict] = {}
        self._history: dict[str, deque[dict]] = {}
        self._history_size = history_size

    def get(self, location_id: str) -> dict | None:
        return self._current.get(location_id)

    def set(self, location_id: str, state: dict) -> None:
        self._current[location_id] = state
        if location_id not in self._history:
            self._history[location_id] = deque(maxlen=self._history_size)
        self._history[location_id].append(state)
        logger.debug("Store updated: %s  temp=%.1f°C  hum=%.1f%%",
                     location_id,
                     state.get("temperature_c", 0),
                     state.get("humidity_pct", 0))

    def get_recent_events(self, location_id: str, n: int = 10) -> list[dict]:
        history = self._history.get(location_id)
        if not history:
            return []
        events = list(history)
        return events[-n:]

    def get_all_location_ids(self) -> list[str]:
        return list(self._current.keys())


# ── Redis implementation (stub) ───────────────────────────────────────────────

class RedisLocationStore(LocationStateStore):
    """
    Redis-backed store — stub showing the upgrade path from InMemoryLocationStore.

    Key layout:
      location:current:{location_id}  →  JSON string of current state dict
      location:history:{location_id}  →  Redis list (LPUSH / LTRIM) of JSON states

    Replace each TODO block with the real redis-py (or aioredis) call.
    The interface above stays identical — EventLoop never changes.

    Parameters
    ──────────
    redis_url    : Redis connection URL, e.g. "redis://localhost:6379/0"
    history_size : Maximum list length to keep per location (via LTRIM).
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 *, history_size: int = 20) -> None:
        self._redis_url = redis_url
        self._history_size = history_size
        self._client = None  # TODO: self._client = redis.from_url(redis_url)
        logger.warning(
            "RedisLocationStore is a stub — no Redis connection has been made. "
            "Install redis-py and replace the TODO blocks."
        )

    def get(self, location_id: str) -> dict | None:
        # TODO: value = self._client.get(f"location:current:{location_id}")
        # TODO: return json.loads(value) if value else None
        raise NotImplementedError("RedisLocationStore.get() is not yet implemented")

    def set(self, location_id: str, state: dict) -> None:
        # TODO: import json
        # TODO: serialized = json.dumps(state)
        # TODO: self._client.set(f"location:current:{location_id}", serialized)
        # TODO: self._client.lpush(f"location:history:{location_id}", serialized)
        # TODO: self._client.ltrim(f"location:history:{location_id}", 0, self._history_size - 1)
        raise NotImplementedError("RedisLocationStore.set() is not yet implemented")

    def get_recent_events(self, location_id: str, n: int = 10) -> list[dict]:
        # TODO: import json
        # TODO: raw = self._client.lrange(f"location:history:{location_id}", 0, n - 1)
        # TODO: return [json.loads(r) for r in reversed(raw)]  # oldest first
        raise NotImplementedError(
            "RedisLocationStore.get_recent_events() is not yet implemented"
        )

    def get_all_location_ids(self) -> list[str]:
        # TODO: keys = self._client.keys("location:current:*")
        # TODO: return [k.decode().split(":")[-1] for k in keys]
        raise NotImplementedError(
            "RedisLocationStore.get_all_location_ids() is not yet implemented"
        )
