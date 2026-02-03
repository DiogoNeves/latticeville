"""Grid-based pathfinding (A*)."""

from __future__ import annotations

from dataclasses import dataclass
import heapq


@dataclass(frozen=True)
class Grid:
    width: int
    height: int
    walls: set[tuple[int, int]]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, x: int, y: int, blocked: set[tuple[int, int]]) -> bool:
        if not self.in_bounds(x, y):
            return False
        if (x, y) in self.walls:
            return False
        if (x, y) in blocked:
            return False
        return True


class PathFinder:
    def __init__(self, grid: Grid) -> None:
        self._grid = grid

    def find_path(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        if start == goal:
            return []
        if not self._grid.is_walkable(*start, blocked):
            return []
        if not self._grid.is_walkable(*goal, blocked):
            return []

        open_set: list[tuple[int, tuple[int, int]]] = []
        heapq.heappush(open_set, (0, start))
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        g_score: dict[tuple[int, int], int] = {start: 0}

        while open_set:
            _, current = heapq.heappop(open_set)
            if current == goal:
                return self._reconstruct_path(came_from, current)

            for neighbor in self._neighbors(current, blocked):
                tentative = g_score[current] + 1
                if tentative < g_score.get(neighbor, 1_000_000):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative
                    f_score = tentative + self._heuristic(neighbor, goal)
                    heapq.heappush(open_set, (f_score, neighbor))

        return []

    def _neighbors(
        self, current: tuple[int, int], blocked: set[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        x, y = current
        candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return [
            pos for pos in candidates if self._grid.is_walkable(pos[0], pos[1], blocked)
        ]

    @staticmethod
    def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _reconstruct_path(
        came_from: dict[tuple[int, int], tuple[int, int] | None],
        current: tuple[int, int],
    ) -> list[tuple[int, int]]:
        path = []
        while current in came_from and came_from[current] is not None:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path
