"""
ogar.world.generic_grid

GenericTerrainGrid — a domain-agnostic 2D grid of GenericCell objects.

What this is
────────────
The spatial backbone of the simulation.  Each cell has coordinates
and a typed CellState that the physics module owns.  The grid knows
about topology (neighbors, bounds, iteration) but never interprets
cell state — that is the physics module's job.

Coordinate system
─────────────────
(row, col) where row 0 is the NORTH edge, col 0 is the WEST edge.
Same convention as the original TerrainGrid so existing scenarios
and wind-direction logic are compatible.

Construction
────────────
The grid takes an initial_state_factory callable (typically
physics.initial_cell_state) that creates the starting CellState
for each cell.  This means the grid doesn't need to know what
domain it's in — the factory injects the domain.

State changes
─────────────
All cell state changes go through update_cell_state().  The engine
calls this after receiving StateEvents from the physics module.
Nothing else should mutate cell state — this enforces the
"physics returns events, engine applies them" contract.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Generic, Iterator, List, Tuple, TypeVar

from ogar.world.cell_state import CellState, GenericCell

C = TypeVar("C", bound=CellState)


class GenericTerrainGrid(Generic[C]):
    """
    Domain-agnostic 2D grid of GenericCell[C] objects.

    Usage
    ─────
      def make_state(row, col) -> MyCellState:
          return MyCellState(elevation=row * 0.1)

      grid = GenericTerrainGrid(rows=10, cols=10, initial_state_factory=make_state)
      cell = grid.get_cell(3, 4)
      print(cell.cell_state)
    """

    def __init__(
        self,
        rows: int,
        cols: int,
        initial_state_factory: Callable[[int, int], C],
    ) -> None:
        """
        Parameters
        ──────────
        rows                  : number of rows (north-south extent)
        cols                  : number of columns (east-west extent)
        initial_state_factory : callable(row, col) → CellState
                                Called once per cell during construction.
                                Typically physics_module.initial_cell_state.
        """
        if rows < 1 or cols < 1:
            raise ValueError(f"Grid dimensions must be positive, got ({rows}, {cols})")
        self.rows = rows
        self.cols = cols
        self._cells: List[List[GenericCell[C]]] = [
            [
                GenericCell(row=r, col=c, cell_state=initial_state_factory(r, c))
                for c in range(cols)
            ]
            for r in range(rows)
        ]

    def get_cell(self, row: int, col: int) -> GenericCell[C]:
        """
        Return the GenericCell at (row, col).

        Raises IndexError if out of bounds.
        """
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise IndexError(
                f"Cell ({row}, {col}) out of bounds for grid ({self.rows}×{self.cols})"
            )
        return self._cells[row][col]

    def neighbors(self, row: int, col: int) -> List[Tuple[int, int]]:
        """
        Return the (row, col) coordinates of all valid 8-connected neighbors.

        Only returns coordinates within grid bounds.  Does NOT filter
        by cell state — the caller (physics module) decides which
        neighbors are relevant.
        """
        result = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    result.append((nr, nc))
        return result

    def update_cell_state(self, row: int, col: int, new_state: C) -> None:
        """
        Replace the cell state at (row, col).

        This is the ONLY sanctioned way to change cell state.  The
        engine calls this after receiving StateEvents from the physics
        module.  Physics modules should never call this directly —
        they return StateEvents and let the engine apply them.
        """
        self._cells[row][col].cell_state = new_state

    def iter_cells(self) -> Iterator[GenericCell[C]]:
        """Iterate over all cells in row-major order."""
        for row in self._cells:
            yield from row

    def cells_where(
        self, predicate: Callable[[GenericCell[C]], bool]
    ) -> List[Tuple[int, int]]:
        """
        Return (row, col) for all cells matching a predicate.

        Example:
          burning = grid.cells_where(
              lambda c: c.cell_state.fire_state == FireState.BURNING
          )
        """
        return [
            (cell.row, cell.col)
            for cell in self.iter_cells()
            if predicate(cell)
        ]

    def snapshot(self) -> Dict[str, Any]:
        """
        Return a complete serialised snapshot of the grid.

        Used for ground truth recording.  Records every cell's state
        so post-scenario analysis can reconstruct the full grid at
        any tick.
        """
        return {
            "rows": self.rows,
            "cols": self.cols,
            "cells": [
                [self._cells[r][c].to_dict() for c in range(self.cols)]
                for r in range(self.rows)
            ],
        }

    def summary_counts(self) -> Dict[str, int]:
        """
        Count cells by their summary_label.

        Returns e.g. {"BURNING": 5, "UNBURNED": 85, "BURNED": 10}
        or {"INFECTED": 20, "HEALTHY": 80} depending on the domain.
        """
        counts: Dict[str, int] = {}
        for cell in self.iter_cells():
            label = cell.cell_state.summary_label()
            counts[label] = counts.get(label, 0) + 1
        return counts
