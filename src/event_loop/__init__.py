"""
event_loop

Plain-Python orchestration layer between sensor data and the agent pipeline.

The event loop knows nothing about LangGraph, agents, or graphs.
It ingests sensor readings, updates location state, runs a deterministic
sensor filter, and delivers batches to a callback.

Public API:
  EventLoop       — main orchestration class
  EventLoopConfig — dataclass for loop configuration
  LocationStateStore   — abstract store interface
  InMemoryLocationStore — in-process implementation
  RedisLocationStore    — Redis stub (shows upgrade path)
  SensorFilter         — abstract filter interface
  ThresholdSensorFilter — default threshold + trend filter
  SensorGenerator      — simulated sensor data for SIMULATION mode
"""

from event_loop.loop import EventLoop as EventLoop
from event_loop.loop import EventLoopConfig as EventLoopConfig
from event_loop.sensor_filter import FilterConfig as FilterConfig
from event_loop.sensor_filter import ScoringFilter as ScoringFilter
from event_loop.sensor_filter import ScoringResult as ScoringResult
from event_loop.sensor_filter import SensorFilter as SensorFilter
from event_loop.sensor_filter import ThresholdSensorFilter as ThresholdSensorFilter
from event_loop.sensor_filter import score_location as score_location
from event_loop.sensor_filter import sensor_filter as sensor_filter
from event_loop.sensor_generator import SensorGenerator as SensorGenerator
from event_loop.store import InMemoryLocationStore as InMemoryLocationStore
from event_loop.store import LocationStateStore as LocationStateStore
from event_loop.store import RedisLocationStore as RedisLocationStore

__all__ = [
    "EventLoop",
    "EventLoopConfig",
    "FilterConfig",
    "LocationStateStore",
    "InMemoryLocationStore",
    "RedisLocationStore",
    "ScoringFilter",
    "ScoringResult",
    "SensorFilter",
    "SensorGenerator",
    "ThresholdSensorFilter",
    "score_location",
    "sensor_filter",
]
