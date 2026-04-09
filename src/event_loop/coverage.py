"""
event_loop.coverage

Sensor coverage validator — deterministic pre-flight check for sensor
colocation quality.

The scoring filter fuses readings from temperature, humidity, and wind
sensors.  If those sensor types aren't close enough to each other in
a given cluster, the fused score is unreliable — it's comparing readings
from different microclimates.

This module answers: "for each cluster, are the required sensor types
collocated well enough to produce meaningful fused data?"

Public API
──────────
    assess_coverage(sensor_inventory, required_types, max_radius)
        → list[ClusterCoverage]

    ClusterCoverage
        .cluster_id
        .quality       — GOOD / SPARSE / INSUFFICIENT
        .max_gap       — worst pairwise distance between required types
        .detail        — per-type-pair distances
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from world.sensor_inventory import SensorInventory


# ── Quality levels ──────────────────────────────────────────────────────────

class CoverageQuality(StrEnum):
    GOOD         = "GOOD"          # All required types within max_radius
    SPARSE       = "SPARSE"        # Some type pairs are distant but present
    INSUFFICIENT = "INSUFFICIENT"  # One or more required types missing entirely


# ── Result types ────────────────────────────────────────────────────────────

@dataclass
class TypePairDistance:
    """Distance between the nearest sensors of two required types."""
    type_a: str
    type_b: str
    min_distance: float          # Euclidean grid distance (cells)
    pos_a: tuple[int, int]       # Position of nearest sensor A
    pos_b: tuple[int, int]       # Position of nearest sensor B


@dataclass
class ClusterCoverage:
    """Coverage assessment for a single cluster."""
    cluster_id: str
    quality: CoverageQuality
    max_gap: float                              # Worst type-pair distance
    missing_types: list[str] = field(default_factory=list)
    pairs: list[TypePairDistance] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.quality == CoverageQuality.INSUFFICIENT:
            return (
                f"[{self.cluster_id}] {self.quality} — "
                f"missing: {', '.join(self.missing_types)}"
            )
        pair_strs = [
            f"{p.type_a}/{p.type_b}={p.min_distance:.1f}"
            for p in self.pairs
        ]
        return (
            f"[{self.cluster_id}] {self.quality} — "
            f"max_gap={self.max_gap:.1f} cells  ({', '.join(pair_strs)})"
        )


# ── Core logic ──────────────────────────────────────────────────────────────

def _euclidean(a: tuple[int, int], b: tuple[int, int]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _min_pairwise_distance(
    positions_a: list[tuple[int, int]],
    positions_b: list[tuple[int, int]],
) -> TypePairDistance | None:
    """Find the closest pair between two sets of positions."""
    best_dist = float("inf")
    best_a = best_b = (0, 0)
    for pa in positions_a:
        for pb in positions_b:
            d = _euclidean(pa, pb)
            if d < best_dist:
                best_dist = d
                best_a, best_b = pa, pb
    if best_dist == float("inf"):
        return None
    return TypePairDistance(
        type_a="", type_b="",  # filled by caller
        min_distance=best_dist,
        pos_a=best_a, pos_b=best_b,
    )


def assess_coverage(
    sensor_inventory: SensorInventory,
    *,
    required_types: tuple[str, ...] = ("temperature", "humidity", "wind"),
    max_radius: float = 4.0,
) -> list[ClusterCoverage]:
    """
    Assess sensor colocation quality per cluster.

    For each cluster, checks whether all required sensor types are present
    and whether the nearest sensors of each required type pair are within
    max_radius grid cells of each other.

    Parameters
    ──────────
    sensor_inventory : The sensor inventory to analyze.
    required_types   : Sensor types that must be collocated for reliable fusion.
    max_radius       : Maximum acceptable distance (Euclidean, in cells)
                       between any two required sensor types.

    Returns
    ───────
    List of ClusterCoverage, one per cluster found in the inventory.
    """
    # Group sensor positions by (cluster_id, source_type)
    cluster_type_positions: dict[str, dict[str, list[tuple[int, int]]]] = {}

    for sensor in sensor_inventory.all_sensors():
        cid = sensor.cluster_id
        stype = sensor.source_type
        pos = (sensor.grid_row, sensor.grid_col)
        cluster_type_positions.setdefault(cid, {}).setdefault(stype, []).append(pos)

    results: list[ClusterCoverage] = []

    for cluster_id, type_positions in sorted(cluster_type_positions.items()):
        # Check for missing types
        missing = [t for t in required_types if t not in type_positions]
        if missing:
            results.append(ClusterCoverage(
                cluster_id=cluster_id,
                quality=CoverageQuality.INSUFFICIENT,
                max_gap=float("inf"),
                missing_types=missing,
            ))
            continue

        # Check pairwise distances between all required type combinations
        pairs: list[TypePairDistance] = []
        max_gap = 0.0

        for i, type_a in enumerate(required_types):
            for type_b in required_types[i + 1:]:
                result = _min_pairwise_distance(
                    type_positions[type_a],
                    type_positions[type_b],
                )
                if result is None:
                    continue
                result.type_a = type_a
                result.type_b = type_b
                pairs.append(result)
                max_gap = max(max_gap, result.min_distance)

        quality = (
            CoverageQuality.GOOD if max_gap <= max_radius
            else CoverageQuality.SPARSE
        )

        results.append(ClusterCoverage(
            cluster_id=cluster_id,
            quality=quality,
            max_gap=max_gap,
            pairs=pairs,
        ))

    return results
