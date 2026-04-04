"""
examples/hello_world.py

The simplest possible demonstration of the sensor → envelope pipeline.

What this proves
────────────────
  1. SensorBase subclass is trivial to implement (just define read()).
  2. SensorEvent envelope is populated correctly from the subclass.
  3. Failure modes (DROPOUT, STUCK) work as expected.
  4. The envelope carries the payload but knows nothing about its content.

Nothing here involves Kafka, LangGraph, or any external service.
Run it with:
  python examples/hello_world.py

Expected output (values will vary — readings are random):
  Tick 0 | source=temp-A1 | cluster=cluster-north | conf=1.00 | payload={'celsius': 23.4, 'fahrenheit': 74.1}
  Tick 1 | source=temp-A1 | cluster=cluster-north | conf=1.00 | payload={'celsius': 31.2, 'fahrenheit': 88.2}
  ... (DROPOUT — sensor silent)
  Tick 4 | source=temp-A1 | cluster=cluster-north | conf=0.30 | payload={'celsius': 28.7, 'fahrenheit': 83.7}
  Tick 5 | source=temp-A1 | cluster=cluster-north | conf=0.30 | payload={'celsius': 28.7, 'fahrenheit': 83.7}
  (STUCK — same value repeated)
  ...
"""

import random
from typing import Dict, Any

# Add the src directory to the path when running the script directly
# (not needed when installed as a package via pip install -e .)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ogar.sensors.base import SensorBase, FailureMode
from ogar.transport.schemas import SensorEvent


# ── Concrete sensor implementation ────────────────────────────────────────────

class MockTemperatureSensor(SensorBase):
    """
    A minimal temperature sensor that returns random values.

    This is purely for demonstration.  In a real scenario the values
    would come from a world simulation engine or replayed historical data.

    The only thing a sensor subclass MUST do is:
      1. Define source_type as a class attribute.
      2. Implement read() returning a plain dict.
    """

    # source_type is the tag that agents use to identify what kind of
    # reading is in the payload.  Lowercase, descriptive.
    source_type = "temperature"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Starting baseline temperature in celsius.
        # Random per instance so two sensors in the same cluster
        # give different readings (more realistic).
        self._baseline_celsius = random.uniform(15.0, 35.0)

    def read(self) -> Dict[str, Any]:
        """
        Return a temperature reading.

        Adds small random noise around the baseline so readings look
        like a real sensor rather than a flat line.

        The envelope will carry whatever we return here — it never
        inspects the keys or values.
        """
        celsius = self._baseline_celsius + random.uniform(-2.0, 2.0)
        fahrenheit = celsius * 9 / 5 + 32
        return {
            "celsius": round(celsius, 1),
            "fahrenheit": round(fahrenheit, 1),
        }


# ── Scenario: run sensor through several failure modes ────────────────────────

def run_scenario():
    sensor = MockTemperatureSensor(
        source_id="temp-A1",
        cluster_id="cluster-north",
        metadata={"location": "ridge-lookout", "elevation_m": 1200},
    )

    print("=== ogar hello world ===")
    print(f"Sensor: {sensor}")
    print()

    # ── Phase 1: Normal operation ─────────────────────────────────────
    print("--- Phase 1: Normal operation ---")
    for _ in range(3):
        _emit_and_print(sensor)

    # ── Phase 2: Dropout (sensor goes silent) ─────────────────────────
    print("\n--- Phase 2: DROPOUT (sensor silent — no events emitted) ---")
    sensor.set_failure_mode(FailureMode.DROPOUT)
    for _ in range(2):
        event = sensor.emit()
        # emit() returns None in dropout mode — nothing to publish
        print(f"  emit() returned: {event}")

    # ── Phase 3: Stuck (frozen reading) ───────────────────────────────
    print("\n--- Phase 3: STUCK (same value repeats, confidence drops) ---")
    sensor.set_failure_mode(FailureMode.STUCK)
    for _ in range(3):
        _emit_and_print(sensor)

    # ── Phase 4: Recovery ─────────────────────────────────────────────
    print("\n--- Phase 4: Recovery (back to NORMAL) ---")
    sensor.set_failure_mode(FailureMode.NORMAL)
    for _ in range(3):
        _emit_and_print(sensor)

    print("\n=== done ===")


def _emit_and_print(sensor: SensorBase) -> None:
    """Emit one event from the sensor and print a summary line."""
    event: SensorEvent = sensor.emit()
    if event is None:
        print("  emit() returned: None")
        return
    print(
        f"  tick={event.sim_tick:02d}"
        f" | source={event.source_id}"
        f" | type={event.source_type}"
        f" | cluster={event.cluster_id}"
        f" | conf={event.confidence:.2f}"
        f" | payload={event.payload}"
    )


if __name__ == "__main__":
    run_scenario()
