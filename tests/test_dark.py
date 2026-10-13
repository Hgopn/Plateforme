import tempfile
import unittest
from collections import deque
from pathlib import Path

from interarcade.app import create_app
from interarcade.config import Config
from interarcade.database import Database
from interarcade.events import event_from_source
from interarcade.games.dark import LEVELS, apply_move, initial_state


class DarkTestConfig(Config):
    SECRET_KEY = "dark-test-secret"
    SESSION_SECRET = "dark-test-session-secret"
    ADMIN_TOKEN = "dark-test-admin"
    INTERNAL_EVENT_TOKEN = "dark-test-internal"
    ALLOWED_ORIGINS = "http://localhost:5000"
    REQUIRE_WORKER_HEARTBEAT = False
    DEMO_MODE = True
    DEMO_TENANT_ID = "dark-test-tenant"
    DEMO_USERNAME = "dark-test-creator"


def route(level, start):
    queue = deque([start])
    previous = {start: None}
    step = {}
    directions = {
        "up": (0, -1),
        "down": (0, 1),
        "left": (-1, 0),
        "right": (1, 0),
    }
    while queue:
        position = queue.popleft()
        if position == level.exit:
            break
        for direction, (dx, dy) in directions.items():
            candidate = (position[0] + dx, position[1] + dy)
            if candidate in previous or level.tiles[candidate[1]][candidate[0]] == "#":
                continue
            previous[candidate] = position
            step[candidate] = direction
            queue.append(candidate)
    if level.exit not in previous:
        raise AssertionError(f"level {level.number} has no route to its exit")
    result = []
    position = level.exit
    while previous[position] is not None:
        result.append(step[position])
        position = previous[position]
    return list(reversed(result))


class DarkRulesTests(unittest.TestCase):
    def test_three_levels_have_expected_sizes_and_reachable_exits(self):
        self.assertEqual([LEVELS[number].size for number in sorted(LEVELS)], [10, 15, 20])
        for level in LEVELS.values():
            self.assertEqual(len(level.tiles), level.size)
            self.assertTrue(all(len(row) == level.size for row in level.tiles))
            self.assertTrue(all(cell == "#" for cell in level.tiles[0] + level.tiles[-1]))
            self.assertEqual(sum(row.count("S") for row in level.tiles), 1)
            self.assertEqual(sum(row.count("E") for row in level.tiles), 1)
            self.assertGreater(len(route(level, level.spawn)), 0)

    def test_labyrinths_have_accessible_branches_dead_ends_and_progressive_detours(self):
        route_lengths = []
        route_turns = []
        for number, minimum_branches, minimum_dead_ends, minimum_loops in (
            (1, 4, 3, 1), (2, 10, 10, 3), (3, 20, 18, 5)
        ):
            level = LEVELS[number]
            open_cells = {
                (x, y)
                for y, row in enumerate(level.tiles)
                for x, cell in enumerate(row)
                if cell != "#"
            }

            def neighbours(position):
                x, y = position
                return [
                    candidate
                    for candidate in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
                    if candidate in open_cells
                ]

            visited = {level.spawn}
            queue = deque([level.spawn])
            while queue:
                for candidate in neighbours(queue.popleft()):
                    if candidate not in visited:
                        visited.add(candidate)
                        queue.append(candidate)
            self.assertEqual(visited, open_cells, f"level {number} has unreachable floor")
            self.assertIn(level.exit, visited)

            degrees = [len(neighbours(position)) for position in open_cells]
            self.assertGreaterEqual(sum(degree >= 3 for degree in degrees), minimum_branches)
            self.assertGreaterEqual(sum(degree == 1 for degree in degrees), minimum_dead_ends)
            self.assertGreaterEqual(sum(degrees) // 2 - len(open_cells) + 1, minimum_loops)
            directions = route(level, level.spawn)
            route_lengths.append(len(directions))
            route_turns.append(sum(a != b for a, b in zip(directions, directions[1:])))

        self.assertEqual(route_lengths, sorted(route_lengths))
        self.assertEqual(route_turns, sorted(route_turns))
        self.assertGreaterEqual(route_lengths[0], 15)
        self.assertGreaterEqual(route_lengths[1], 30)
        self.assertGreaterEqual(route_lengths[2], 55)

    def test_collisions_do_not_change_position_or_move_count(self):
        state = initial_state()
        collided, outcome = apply_move(state, "up")
        self.assertEqual(collided, state)
        self.assertTrue(outcome["collision"])
        self.assertFalse(outcome["moved"])
        with self.assertRaisesRegex(ValueError, "invalid direction"):
            apply_move(state, "diagonal")
        outside = {**state, "player_x": 0, "player_y": 0}
        self.assertTrue(apply_move(outside, "left")[1]["collision"])

    def test_progression_runs_from_level_one_through_three(self):
        state = initial_state()
        transitions = []
        for number in (1, 2, 3):
            level = LEVELS[number]
            for direction in route(level, (state["player_x"], state["player_y"])):
                state, outcome = apply_move(state, direction)
                if outcome["transition"]:
                    transitions.append(outcome["transition"])
        self.assertEqual([item["type"] for item in transitions], ["level_complete", "level_complete", "game_complete"])
        self.assertEqual(state["level"], 3)
        self.assertEqual(state["status"], "finished")

    def test_provider_neutral_event_contract(self):
        event = event_from_source("test", "tenant", "session", "like", "viewer", count=3)
        self.assertEqual(event.source, "test")
        event = event_from_source("future-provider", "tenant", "session", "follow", "viewer")
        self.assertEqual(event.to_dict()["source"], "future-provider")


class DarkRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        DarkTestConfig.DATABASE_URL = f"sqlite:///{Path(self.temp_dir.name) / 'dark.sqlite'}"
        self.app = create_app(DarkTestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_session(self):
        response = self.client.post("/api/v1/demo/session", json={"game_id": "dark"})
        self.assertEqual(response.status_code, 201)
        session = response.get_json()
        return session, {"Authorization": f"Bearer {session['token']}"}

    def test_start_collision_reset_and_session_close(self):
        session, headers = self.create_session()
        base = f"/api/v1/sessions/{session['session_id']}/games/dark"
        started = self.client.post(f"{base}/start", headers=headers)
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.get_json()["state"]["map"]["width"], 10)

        collision = self.client.post(f"{base}/move", headers=headers, json={"direction": "up"})
        self.assertEqual(collision.status_code, 200)
        self.assertTrue(collision.get_json()["outcome"]["collision"])
        moved = self.client.post(f"{base}/move", headers=headers, json={"direction": "right"})
        self.assertEqual(moved.get_json()["state"]["moves"], 1)

        reset = self.client.post(f"{base}/reset", headers=headers)
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.get_json()["state"]["level"], 1)
        self.assertEqual(reset.get_json()["state"]["moves"], 0)
        self.assertEqual(reset.get_json()["state"]["player"], {"x": 1, "y": 1})

        event = self.client.post(
            "/api/v1/demo/events",
            json={
                "session_id": session["session_id"],
                "type": "like",
                "actor": "test-viewer",
                "payload": {"count": 2},
            },
        )
        self.assertEqual(event.status_code, 202)
        self.assertEqual(event.get_json()["source"], "test")

        ended = self.client.post(f"/api/v1/sessions/{session['session_id']}/end", headers=headers)
        self.assertEqual(ended.status_code, 200)
        state = self.client.get(f"{base}/state", headers=headers).get_json()["state"]
        self.assertEqual(state["status"], "ended")
        blocked = self.client.post(f"{base}/move", headers=headers, json={"direction": "right"})
        self.assertEqual(blocked.status_code, 401)

    def test_dark_routes_reject_other_game_sessions(self):
        session = self.client.post("/api/v1/demo/session", json={"game_id": "slot"}).get_json()
        response = self.client.post(
            f"/api/v1/sessions/{session['session_id']}/games/dark/start",
            headers={"Authorization": f"Bearer {session['token']}"},
        )
        self.assertEqual(response.status_code, 401)

    def test_database_reset_persists_after_reopen(self):
        database = self.app.extensions["database"]
        database.save_session("persisted-dark", "dark-test-tenant", "dark")
        database.start_dark_run("run-one", "persisted-dark")
        database.move_dark("persisted-dark", "right")
        database.start_dark_run("ignored-on-reset", "persisted-dark", reset=True)
        reopened = Database(DarkTestConfig.DATABASE_URL)
        state = reopened.dark_run("persisted-dark")
        self.assertEqual((state["level"], state["player_x"], state["moves"]), (1, 1, 0))

    def test_api_progression_completion_and_restart(self):
        session, headers = self.create_session()
        base = f"/api/v1/sessions/{session['session_id']}/games/dark"
        started = self.client.post(f"{base}/start", headers=headers).get_json()["state"]
        current = started
        for number in (1, 2, 3):
            self.assertEqual(current["map"]["width"], LEVELS[number].size)
            directions = route(LEVELS[number], (current["player"]["x"], current["player"]["y"]))
            for direction in directions:
                response = self.client.post(f"{base}/move", headers=headers, json={"direction": direction})
                self.assertEqual(response.status_code, 200)
                result = response.get_json()
                current = result["state"]
            self.assertEqual(result["outcome"]["transition"]["completed_level"], number)
            if number < 3:
                self.assertEqual(current["level"], number + 1)
                self.assertEqual(result["outcome"]["transition"]["next_level"], number + 1)
        self.assertEqual(current["status"], "finished")
        self.assertEqual(result["outcome"]["transition"]["type"], "game_complete")
        self.assertEqual(self.client.get(f"{base}/state", headers=headers).get_json()["state"], current)
        no_more_moves = self.client.post(f"{base}/move", headers=headers, json={"direction": "left"})
        self.assertFalse(no_more_moves.get_json()["outcome"]["moved"])
        self.assertEqual(no_more_moves.get_json()["state"], current)
        restarted = self.client.post(f"{base}/reset", headers=headers).get_json()["state"]
        self.assertEqual((restarted["level"], restarted["moves"], restarted["status"]), (1, 0, "active"))
        self.assertEqual(restarted["player"], {"x": 1, "y": 1})
        self.assertEqual(self.app.extensions["database"].dark_run(session["session_id"])["status"], "active")
        self.client.post(f"/api/v1/sessions/{session['session_id']}/end", headers=headers)
        self.assertEqual(self.app.extensions["database"].dark_run(session["session_id"])["status"], "ended")


if __name__ == "__main__":
    unittest.main()
