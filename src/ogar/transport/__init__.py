"""
ogar.transport

Everything related to moving events between components.

Modules:
  schemas.py  ← The SensorEvent envelope — the single shared contract
                between sensors, the bridge consumer, and agents.
  topics.py   ← Kafka topic name constants and a helper to build
                the per-cluster topic name from a cluster_id.

Nothing in this package knows about LangGraph, sensors, or actuators.
It is pure data contract + naming conventions.
"""
