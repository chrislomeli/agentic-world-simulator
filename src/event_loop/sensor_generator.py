"""
event_loop.sensor_generator

Simulated sensor data generator for the SIMULATION mode event loop.

Generates plausible wildfire risk readings per location.  Readings vary
around a baseline appropriate to each location and occasionally spike into
high-risk ranges to trigger the sensor filter and exercise the agent pipeline.

Real-world reference values
───────────────────────────
  Temperature:   15–40°C normal, 40°C+ high risk
  Humidity:      30–80% normal, <15% extreme fire danger
  Wind speed:    0–8 m/s normal, >10 m/s high risk
  Fuel moisture: 10–30% normal, <8% extreme fire danger
  Slope:         fixed terrain feature, not time-varying

Spike model
───────────
Each reading has a small probability of spiking into a high-risk range.
Spikes are independent per sensor type.  This ensures that the sensor
filter will occasionally see readings that cross its thresholds.

Usage
─────
  gen = SensorGenerator(location_ids=["loc-A", "loc-B"])
  reading = gen.generate("loc-A")
  # {"location_id": "loc-A", "temperature_c": 31.2, "humidity_pct": 22.4, ...}
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Default baseline conditions per sensor type ───────────────────────────────
# Each location starts from these and drifts slightly over time.

_DEFAULT_BASELINES: dict[str, dict[str, float]] = {
    "temperature_c":      {"mean": 28.0, "std": 3.0,  "spike_value": 42.0, "spike_prob": 0.05},
    "humidity_pct":       {"mean": 35.0, "std": 8.0,  "spike_value": 8.0,  "spike_prob": 0.05},
    "wind_speed_mps":     {"mean": 4.0,  "std": 1.5,  "spike_value": 14.0, "spike_prob": 0.04},
    "wind_direction_deg": {"mean": 225.0, "std": 20.0, "spike_value": None, "spike_prob": 0.0},
    "fuel_moisture_pct":  {"mean": 12.0, "std": 3.0,  "spike_value": 5.0,  "spike_prob": 0.04},
}

# Slope is fixed terrain — assigned once per location, not time-varying.
_SLOPE_RANGE = (0.0, 30.0)


class SensorGenerator:
    """
    Generates simulated sensor readings for a set of locations.

    Each location has independently varying baselines with occasional spikes
    into high-risk ranges.  Slope is assigned once at construction and is
    constant (it models terrain, not weather).

    Parameters
    ──────────
    location_ids : List of location identifiers to generate readings for.
    seed         : Optional random seed for reproducibility in tests.
    """

    def __init__(
        self,
        location_ids: list[str],
        *,
        seed: int | None = None,
    ) -> None:
        if seed is not None:
            random.seed(seed)

        # Assign each location a fixed slope and slight baseline offset
        # so that locations behave differently from one another.
        self._location_meta: dict[str, dict[str, Any]] = {}
        for loc_id in location_ids:
            self._location_meta[loc_id] = {
                "slope_deg": round(random.uniform(*_SLOPE_RANGE), 1),
                # Small per-location offset so readings aren't identical
                "temp_offset": random.uniform(-5.0, 5.0),
                "hum_offset": random.uniform(-10.0, 10.0),
            }

        logger.info(
            "SensorGenerator initialized for %d location(s): %s",
            len(location_ids),
            location_ids,
        )

    def generate(self, location_id: str) -> dict[str, Any]:
        """
        Generate one sensor reading for the given location.

        Returns a location state dict ready to be stored in LocationStateStore.

        Raises KeyError if location_id was not in the constructor's location_ids.
        """
        meta = self._location_meta.get(location_id)
        if meta is None:
            raise KeyError(f"Unknown location_id: {location_id!r}")

        def _sample(field: str, offset: float = 0.0) -> float:
            cfg = _DEFAULT_BASELINES[field]
            if cfg["spike_prob"] > 0 and random.random() < cfg["spike_prob"]:
                # Spike — jump to the high-risk value with some noise
                value = cfg["spike_value"] + random.gauss(0, cfg["std"] * 0.5)
                logger.debug("SensorGenerator spike: %s  %s=%.1f", location_id, field, value)
            else:
                value = random.gauss(cfg["mean"] + offset, cfg["std"])
            return value

        temperature_c  = round(_sample("temperature_c",  meta["temp_offset"]), 1)
        humidity_pct   = round(max(1.0, min(100.0, _sample("humidity_pct", meta["hum_offset"]))), 1)
        wind_speed_mps = round(max(0.0, _sample("wind_speed_mps")), 1)
        wind_dir_deg   = round(_sample("wind_direction_deg") % 360.0, 1)
        fuel_moisture  = round(max(1.0, _sample("fuel_moisture_pct")), 1)

        return {
            "location_id":        location_id,
            "temperature_c":      temperature_c,
            "humidity_pct":       humidity_pct,
            "wind_speed_mps":     wind_speed_mps,
            "wind_direction_deg": wind_dir_deg,
            "fuel_moisture_pct":  fuel_moisture,
            "slope_deg":          meta["slope_deg"],
            "timestamp":          datetime.now(UTC).isoformat(),
        }
