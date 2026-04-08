"""
event_loop.sensor_filter

Deterministic pre-filter that decides whether a location's recent readings
warrant invoking the (expensive) LLM agent pipeline.

Scoring model
─────────────
Each risk condition (high temperature, low humidity, etc.) contributes a
weighted score when it crosses its threshold.  The location triggers only
when the total score exceeds a configurable trigger threshold.

This is sensor fusion: "we only invoke the AI when multiple risk factors
are elevated simultaneously."  A single elevated reading is not enough —
the filter requires convergent evidence before spending money on an LLM call.

Example:
  temperature 42°C  →  score 1.0 × weight 1.0  =  1.0
  humidity 10%      →  score 1.0 × weight 1.2  =  1.2
  wind 6 m/s        →  below threshold          =  0.0
  fuel moisture 7%  →  score 1.0 × weight 1.5  =  1.5
  slope 5°          →  below threshold          =  0.0
  total = 3.7  >  trigger_threshold 2.0  →  TRIGGERED

All thresholds and weights live in FilterConfig at the top of this file.
To tune sensitivity, adjust the weights or trigger_threshold — no code
changes needed.

What it is NOT for
──────────────────
  - Pattern recognition across locations (→ supervisor)
  - Probabilistic risk scoring with ML (→ cluster agent with LLM)
  - Anything that requires an API call

Public API
──────────
  score_location(state, config)  →  ScoringResult (full breakdown)
  ScoringFilter                  →  SensorFilter using the scoring model
  sensor_filter(state)           →  bool (convenience, uses default config)

Usage
─────
  filt = ScoringFilter()
  triggered, reason = filt.should_trigger(recent_events)

  # Or for the full breakdown (useful for cluster agent context):
  result = score_location(state, config)
  result.total_score   # 3.7
  result.triggered     # True
  result.conditions    # [("temperature_c", 1.0, "42.0°C > 38.0°C"), ...]
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────
# All thresholds and weights in one place.  To tune the filter's sensitivity,
# adjust these values — no structural changes needed.

@dataclass
class FilterConfig:
    """
    Thresholds, weights, and trigger sensitivity for the sensor filter.

    Each condition has:
      - threshold: the value at which the condition starts contributing
      - weight: how much it contributes to the total score (higher = more important)

    The location triggers when the total weighted score exceeds trigger_threshold.

    Metric units throughout (°C, %, m/s, degrees) to match the sensor generator
    and the rest of the codebase.

    Tuning guide
    ────────────
    - Lower trigger_threshold → more sensitive (more triggers, more LLM calls)
    - Higher trigger_threshold → less sensitive (fewer triggers, may miss events)
    - Increase a weight → that condition has more influence on triggering
    - trigger_threshold=1.0 means any single condition can trigger alone
      (if its weight ≥ 1.0)
    - trigger_threshold=2.0 means at least two conditions must be elevated
    """
    # ── Thresholds ────────────────────────────────────────────────────
    temp_high_c:          float = 38.0   # °C — above this → elevated fire danger
    humidity_low_pct:     float = 15.0   # % — below this → extreme fire danger
    wind_high_mps:        float = 10.0   # m/s — above this → rapid spread potential
    fuel_moisture_low_pct: float = 8.0   # % — below this → extreme ignition risk
    slope_high_deg:       float = 20.0   # ° — above this → fire accelerates uphill

    # ── Weights (how much each condition contributes to the score) ────
    temp_weight:          float = 1.0
    humidity_weight:      float = 1.2    # Low humidity is a strong fire signal
    wind_weight:          float = 1.0
    fuel_moisture_weight: float = 1.5    # Dry fuel is the strongest predictor
    slope_weight:         float = 0.8    # Slope is terrain, not weather — lower weight

    # ── Trigger sensitivity ───────────────────────────────────────────
    trigger_threshold:    float = 2.0    # Total score must exceed this to trigger

    # ── Trend detection ───────────────────────────────────────────────
    trend_window:         int   = 3      # Consecutive readings for trend detection
    trend_weight:         float = 0.7    # How much a trend contributes per condition


# ── Default config instance ───────────────────────────────────────────────────
DEFAULT_CONFIG = FilterConfig()


# ── Scoring result ────────────────────────────────────────────────────────────

@dataclass
class ScoringResult:
    """
    Full scoring breakdown for a single location reading.

    Returned by score_location() so the cluster agent can see exactly
    why a location was flagged (or not).

    Attributes
    ──────────
    location_id  : Which location was scored.
    total_score  : Sum of all weighted condition scores.
    triggered    : Whether total_score > trigger_threshold.
    threshold    : The trigger_threshold used.
    conditions   : List of (condition_name, weighted_score, detail_str)
                   for every condition that scored > 0.
    """
    location_id: str
    total_score: float
    triggered: bool
    threshold: float
    conditions: list[tuple[str, float, str]] = field(default_factory=list)

    @property
    def reason(self) -> str:
        """Human-readable trigger reason for logging."""
        if not self.triggered:
            return f"score {self.total_score:.2f} < {self.threshold:.1f} — within normal range"
        parts = [f"{name}: {detail}" for name, _, detail in self.conditions]
        return (
            f"score {self.total_score:.2f} > {self.threshold:.1f} — "
            + "; ".join(parts)
        )


# ── Scoring function ─────────────────────────────────────────────────────────

def score_location(
    state: dict,
    config: FilterConfig = DEFAULT_CONFIG,
) -> ScoringResult:
    """
    Score a single location reading against all risk conditions.

    Pure function — no side effects, same input always gives same output.

    Parameters
    ──────────
    state  : Location state dict with sensor readings.
    config : FilterConfig with thresholds and weights.

    Returns
    ───────
    ScoringResult with the full breakdown.
    """
    location_id = state.get("location_id", "unknown")
    conditions: list[tuple[str, float, str]] = []
    total = 0.0

    # ── Temperature ───────────────────────────────────────────────────
    temp = state.get("temperature_c", 0.0)
    if temp > config.temp_high_c:
        score = config.temp_weight
        conditions.append(("temperature_c", score, f"{temp:.1f}°C > {config.temp_high_c:.1f}°C"))
        total += score

    # ── Humidity (inverted — lower is worse) ──────────────────────────
    hum = state.get("humidity_pct", 100.0)
    if hum < config.humidity_low_pct:
        score = config.humidity_weight
        conditions.append(("humidity_pct", score, f"{hum:.1f}% < {config.humidity_low_pct:.1f}%"))
        total += score

    # ── Wind speed ────────────────────────────────────────────────────
    wind = state.get("wind_speed_mps", 0.0)
    if wind > config.wind_high_mps:
        score = config.wind_weight
        conditions.append(("wind_speed_mps", score, f"{wind:.1f} m/s > {config.wind_high_mps:.1f} m/s"))
        total += score

    # ── Fuel moisture (inverted — lower is worse) ─────────────────────
    fuel = state.get("fuel_moisture_pct", 100.0)
    if fuel < config.fuel_moisture_low_pct:
        score = config.fuel_moisture_weight
        conditions.append(("fuel_moisture_pct", score, f"{fuel:.1f}% < {config.fuel_moisture_low_pct:.1f}%"))
        total += score

    # ── Slope ─────────────────────────────────────────────────────────
    slope = state.get("slope_deg", 0.0)
    if slope > config.slope_high_deg:
        score = config.slope_weight
        conditions.append(("slope_deg", score, f"{slope:.1f}° > {config.slope_high_deg:.1f}°"))
        total += score

    triggered = total > config.trigger_threshold
    return ScoringResult(
        location_id=location_id,
        total_score=total,
        triggered=triggered,
        threshold=config.trigger_threshold,
        conditions=conditions,
    )


# ── Convenience function ──────────────────────────────────────────────────────

def sensor_filter(state: dict, config: FilterConfig = DEFAULT_CONFIG) -> bool:
    """
    Quick trigger check — returns True if the location should be flagged.

    Importable as: from event_loop.sensor_filter import sensor_filter
    """
    return score_location(state, config).triggered


# ── SensorFilter ABC and scoring implementation ──────────────────────────────

class SensorFilter(ABC):
    """
    Abstract sensor filter interface.

    Implementations decide whether recent readings for a location are
    interesting enough to invoke the agent pipeline.
    """

    @abstractmethod
    def should_trigger(
        self,
        recent_events: list[dict],
    ) -> tuple[bool, str]:
        """
        Evaluate recent readings for a single location.

        Parameters
        ──────────
        recent_events : List of state dicts, oldest first.
                        At least one entry is guaranteed.

        Returns
        ───────
        (triggered, reason) — triggered=True means this location should
        be included in the next agent batch.  reason is a human-readable
        explanation for logging.
        """


class ScoringFilter(SensorFilter):
    """
    Sensor filter using the weighted scoring model.

    Each risk condition contributes a weighted score when it crosses its
    threshold.  The location triggers only when the total score exceeds
    the trigger_threshold — this is sensor fusion.

    Also checks for trends: if a condition has been worsening over the
    last N readings (approaching its threshold), it contributes a smaller
    trend score.  This catches situations that are deteriorating but
    haven't yet crossed the threshold.

    Parameters
    ──────────
    config : FilterConfig with all thresholds, weights, and sensitivity.
             Defaults to DEFAULT_CONFIG.
    """

    def __init__(self, config: FilterConfig | None = None) -> None:
        self._config = config or DEFAULT_CONFIG

    def should_trigger(self, recent_events: list[dict]) -> tuple[bool, str]:
        if not recent_events:
            return False, "no data"

        latest = recent_events[-1]

        # ── Score the latest reading ──────────────────────────────────
        result = score_location(latest, self._config)

        # ── Add trend scores from recent history ──────────────────────
        trend_conditions = self._check_trends(recent_events)
        for name, score, detail in trend_conditions:
            result.conditions.append((name, score, detail))
            result.total_score += score

        # Re-evaluate trigger after adding trends
        result.triggered = result.total_score > self._config.trigger_threshold

        if result.triggered:
            logger.info(
                "TRIGGERED [%s]  %s",
                result.location_id,
                result.reason,
            )

        return result.triggered, result.reason

    def _check_trends(
        self,
        recent_events: list[dict],
    ) -> list[tuple[str, float, str]]:
        """
        Check for deteriorating trends in the recent history.

        A trend scores if the condition has been monotonically worsening
        for the last trend_window readings AND the latest value is
        approaching the threshold (within 85% of it).
        """
        cfg = self._config
        trends: list[tuple[str, float, str]] = []

        if len(recent_events) < cfg.trend_window:
            return trends

        window = recent_events[-cfg.trend_window:]

        # Rising temperature trend
        temps = [e.get("temperature_c", 0.0) for e in window]
        if (all(temps[i] < temps[i + 1] for i in range(len(temps) - 1))
                and temps[-1] > cfg.temp_high_c * 0.85):
            trends.append((
                "temperature_trend",
                cfg.trend_weight,
                f"rising {temps[0]:.1f} → {temps[-1]:.1f}°C",
            ))

        # Falling humidity trend
        hums = [e.get("humidity_pct", 100.0) for e in window]
        if (all(hums[i] > hums[i + 1] for i in range(len(hums) - 1))
                and hums[-1] < cfg.humidity_low_pct * 1.5):
            trends.append((
                "humidity_trend",
                cfg.trend_weight,
                f"falling {hums[0]:.1f} → {hums[-1]:.1f}%",
            ))

        # Rising wind trend
        winds = [e.get("wind_speed_mps", 0.0) for e in window]
        if (all(winds[i] < winds[i + 1] for i in range(len(winds) - 1))
                and winds[-1] > cfg.wind_high_mps * 0.85):
            trends.append((
                "wind_trend",
                cfg.trend_weight,
                f"rising {winds[0]:.1f} → {winds[-1]:.1f} m/s",
            ))

        # Falling fuel moisture trend
        fuels = [e.get("fuel_moisture_pct", 100.0) for e in window]
        if (all(fuels[i] > fuels[i + 1] for i in range(len(fuels) - 1))
                and fuels[-1] < cfg.fuel_moisture_low_pct * 1.5):
            trends.append((
                "fuel_moisture_trend",
                cfg.trend_weight,
                f"falling {fuels[0]:.1f} → {fuels[-1]:.1f}%",
            ))

        return trends


# ── Backwards compatibility ───────────────────────────────────────────────────
# ThresholdSensorFilter is now an alias for ScoringFilter.
ThresholdSensorFilter = ScoringFilter
