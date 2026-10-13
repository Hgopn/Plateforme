"""Server-authoritative rules and maps for the first Dark campaign."""

from __future__ import annotations

from dataclasses import dataclass


DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


@dataclass(frozen=True)
class DarkLevel:
    number: int
    size: int
    tiles: tuple[str, ...]
    spawn: tuple[int, int]
    exit: tuple[int, int]

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "width": self.size,
            "height": self.size,
            "tiles": list(self.tiles),
            "spawn": {"x": self.spawn[0], "y": self.spawn[1]},
            "exit": {"x": self.exit[0], "y": self.exit[1]},
        }


def _level(number: int, rows: tuple[str, ...]) -> DarkLevel:
    """Keep the authored labyrinth readable alongside its server rules."""
    spawn = next((x, y) for y, row in enumerate(rows) for x, cell in enumerate(row) if cell == "S")
    exit_position = next((x, y) for y, row in enumerate(rows) for x, cell in enumerate(row) if cell == "E")
    return DarkLevel(
        number=number,
        size=len(rows),
        tiles=rows,
        spawn=spawn,
        exit=exit_position,
    )


LEVELS = {
    1: _level(1, (
        "##########",
        "#S..#.#.##",
        "###.#.#.##",
        "#.......##",
        "#.#####.##",
        "#...#...##",
        "#.###.####",
        "#........#",
        "########E#",
        "##########",
    )),
    2: _level(2, (
        "###############",
        "#S#.......#...#",
        "#.#####.#####.#",
        "#.........#.#.#",
        "#.###.#####.#.#",
        "#...#.#.......#",
        "#.#.#.#.#.###.#",
        "#...#...#.#...#",
        "#.###.#####.###",
        "#...#.#.....#.#",
        "#.#.#.###.###.#",
        "#.#...#.#.....#",
        "#.###.#.###.#.#",
        "#...#.#......E#",
        "###############",
    )),
    3: _level(3, (
        "####################",
        "#S#...............##",
        "#.#####.#####.###.##",
        "#.#.#...#.#...#.#.##",
        "#.#.#.#.#.#.###.#.##",
        "#.....#...#...#...##",
        "#.###.#.###.#####.##",
        "#.#...#.#.....#...##",
        "###.#########.###.##",
        "#...#.#.#...#.....##",
        "#####.#.#.#.#.######",
        "#.....#...#.......##",
        "#.###.#.#.##########",
        "#...#.......#.....##",
        "###.###.#.#.#.#.#.##",
        "#...#.......#.#...##",
        "#.#####.#####.#.#.##",
        "#.....#.......#.#..#",
        "##################E#",
        "####################",
    )),
}


def level_definition(number: int) -> DarkLevel:
    try:
        return LEVELS[int(number)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("unknown Dark level") from exc


def initial_state() -> dict:
    level = level_definition(1)
    return {
        "level": level.number,
        "status": "active",
        "player_x": level.spawn[0],
        "player_y": level.spawn[1],
        "moves": 0,
    }


def public_state(state: dict | None) -> dict | None:
    if not state:
        return None
    level = level_definition(state["level"])
    return {
        "status": state["status"],
        "level": int(state["level"]),
        "level_count": len(LEVELS),
        "player": {
            "x": int(state["player_x"]),
            "y": int(state["player_y"]),
        },
        "moves": int(state["moves"]),
        "map": level.to_dict(),
    }


def apply_move(state: dict, direction: str) -> tuple[dict, dict]:
    """Apply one grid step and return the next state plus a movement outcome."""
    if direction not in DIRECTIONS:
        raise ValueError("invalid direction")
    if state["status"] != "active":
        return state, {"moved": False, "collision": False, "transition": None}

    level = level_definition(state["level"])
    dx, dy = DIRECTIONS[direction]
    next_x = int(state["player_x"]) + dx
    next_y = int(state["player_y"]) + dy
    if not 0 <= next_x < level.size or not 0 <= next_y < level.size or level.tiles[next_y][next_x] == "#":
        return state, {"moved": False, "collision": True, "transition": None}

    next_state = {
        **state,
        "player_x": next_x,
        "player_y": next_y,
        "moves": int(state["moves"]) + 1,
    }
    transition = None
    if (next_x, next_y) == level.exit:
        if level.number < len(LEVELS):
            next_level = level_definition(level.number + 1)
            next_state.update(
                level=next_level.number,
                player_x=next_level.spawn[0],
                player_y=next_level.spawn[1],
            )
            transition = {
                "type": "level_complete",
                "completed_level": level.number,
                "next_level": next_level.number,
            }
        else:
            next_state["status"] = "finished"
            transition = {"type": "game_complete", "completed_level": level.number}
    return next_state, {"moved": True, "collision": False, "transition": transition}
