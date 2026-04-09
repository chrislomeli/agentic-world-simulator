#!/usr/bin/env python3
"""
render.py — ASCII grid rendering utilities shared across tutorial steps.

Three focused renderers, each printing its own grid:

    render_terrain(engine)
        Terrain and fire state only.  No sensors, no resources.

    render_sensors(engine, sensor_inventory, layers=None)
        Terrain + sensor positions.  Pass layers=[...] to show a subset.

    render_resources(engine, resource_inventory)
        Terrain + response-asset positions and types.

    render_grid(engine, sensor_inventory=None, resource_inventory=None)
        Convenience wrapper — calls whichever renderers have data.

All renderers print to stdout.  Fire state (F=burning, *=burned) always
takes priority over sensor and resource glyphs.
"""

from world.grid import FireState, TerrainType

# ── Shared glyph tables ───────────────────────────────────────────────────────

_TERRAIN_GLYPH = {
    TerrainType.FOREST:    "T",
    TerrainType.GRASSLAND: ".",
    TerrainType.ROCK:      "#",
    TerrainType.WATER:     "~",
    TerrainType.SCRUB:     "s",
    TerrainType.URBAN:     "U",
}

_SENSOR_GLYPH = {
    "temperature":        "t",
    "smoke":              "k",
    "humidity":           "h",
    "wind":               "w",
    "barometric_pressure":"b",
    "thermal_camera":     "c",
}

_RESOURCE_GLYPH = {
    "hospital":   "H",
    "ambulance":  "A",
    "engine":     "E",
    "crew":       "C",
    "dozer":      "D",
    "helicopter": "^",
    "scooper":    "W",
}

_TERRAIN_LEGEND   = "T=Forest  .=Grass  #=Rock  ~=Water  s=Scrub  U=Urban  F=Burning  *=Burned"
_SENSOR_LEGEND    = "t=temp  k=smoke  h=humidity  w=wind  b=barometric  c=camera  +=overlap"
_RESOURCE_LEGEND  = "H=hospital  A=ambulance  E=engine  C=crew  D=dozer  ^=helicopter  W=scooper  +=overlap"


# ── Shared draw helper ────────────────────────────────────────────────────────

def _draw_grid(engine, overrides: dict[tuple[int, int], str], *, terrain: bool = True) -> None:
    """
    Print the grid as ASCII art.

    Fire state (burning/burned) always wins over any override glyph.
    overrides maps (row, col) → glyph for sensors or resources.
    When terrain=False, empty cells show as '.' instead of their terrain type.
    """
    print("  " + " ".join(str(c) for c in range(engine.grid.cols)))
    for row_idx in range(engine.grid.rows):
        row = []
        for col_idx in range(engine.grid.cols):
            cell  = engine.grid.get_cell(row_idx, col_idx)
            state = cell.cell_state
            if state.fire_state == FireState.BURNING:
                glyph = "F"
            elif state.fire_state == FireState.BURNED:
                glyph = "*"
            elif (row_idx, col_idx) in overrides:
                glyph = overrides[(row_idx, col_idx)]
            elif terrain:
                glyph = _TERRAIN_GLYPH.get(state.terrain_type, "?")
            else:
                glyph = "."
            row.append(glyph)
        print(f"{row_idx} {' '.join(row)}")
    print()


# ── Public renderers ──────────────────────────────────────────────────────────

def render_terrain(engine) -> None:
    """Print terrain and fire state only — no sensors, no resources."""
    print("--- Terrain ---")
    _draw_grid(engine, {})
    print(f"Legend: {_TERRAIN_LEGEND}")
    print()


def render_sensors(engine, sensor_inventory, layers=None) -> None:
    """
    Print terrain with sensor positions overlaid.

    Parameters
    ──────────
    sensor_inventory : SensorInventory — provides positions per layer type.
    layers           : optional list of source_type strings to show (e.g. ["smoke"]).
                       If None, all sensor types are shown.
    """
    positions: dict[tuple[int, int], str] = {}
    show_types = set(layers) if layers else sensor_inventory.layer_types()
    for stype in show_types:
        for pos in sensor_inventory.layer_positions(stype):
            rc = (pos[0], pos[1])
            positions[rc] = "+" if rc in positions else _SENSOR_GLYPH.get(stype, "?")

    print("--- Sensors ---")
    _draw_grid(engine, positions, terrain=False)
    print(f"Sensors: {_SENSOR_LEGEND}  F=Burning  *=Burned")
    print()


def render_resources(engine, resource_inventory) -> None:
    """
    Print terrain with response-asset positions overlaid.

    Multiple resources at the same cell are shown as '+'.
    """
    positions: dict[tuple[int, int], str] = {}
    for r in resource_inventory.all_resources():
        rc = (r.grid_row, r.grid_col)
        positions[rc] = "+" if rc in positions else _RESOURCE_GLYPH.get(r.resource_type, "R")

    print("--- Resources ---")
    _draw_grid(engine, positions, terrain=False)
    print(f"Resources: {_RESOURCE_LEGEND}  F=Burning  *=Burned")
    print()


def render_grid(engine, sensor_inventory=None, resource_inventory=None) -> None:
    """
    Render all available layers: terrain, then sensors, then resources.

    Skips sensor or resource layers if the corresponding inventory is None.
    """
    render_terrain(engine)
    if sensor_inventory is not None:
        render_sensors(engine, sensor_inventory)
    if resource_inventory is not None:
        render_resources(engine, resource_inventory)
