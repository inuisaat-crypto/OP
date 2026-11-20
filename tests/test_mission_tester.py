import asyncio
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mission_format import load_mission
from mission_tester import (
    _prepare_bluetooth_program,
    _wait_for_program_stop,
    discover_missions,
    expected_pose,
    expected_poses,
    run_dry_run,
)


class MissionTesterTests(unittest.TestCase):
    def test_discovers_mission_json_files_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mission_2.json").write_text("{}", encoding="utf-8")
            (root / "settings.json").write_text("{}", encoding="utf-8")
            (root / "mission_1.json").write_text("{}", encoding="utf-8")

            names = [path.name for path in discover_missions(root)]

        self.assertEqual(names, ["mission_1.json", "mission_2.json"])

    def test_existing_mission_has_expected_final_pose(self):
        path = Path(__file__).resolve().parents[1] / "mission_1.json"
        mission = load_mission(path)

        x, y, heading = expected_pose(mission)

        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, 25.0, places=6)
        self.assertAlmostEqual(heading, 180.0, places=6)

    def test_mission_3_turns_then_moves_forward_and_reverses_attachment(self):
        path = Path(__file__).resolve().parents[1] / "mission_3.json"
        mission = load_mission(path)
        steps = mission["steps"]

        self.assertEqual(steps[0]["distance_mm"], 550)
        self.assertEqual(steps[1]["distance_mm"], -200)
        self.assertEqual(steps[2]["type"], "turn")
        self.assertEqual(steps[2]["angle_deg"], 45)
        self.assertEqual(steps[3]["distance_mm"], 300)
        self.assertEqual(steps[4]["type"], "turn")
        self.assertEqual(steps[4]["angle_deg"], -45)
        self.assertEqual(steps[6]["port"], "F")
        self.assertEqual(steps[6]["angle_deg"], -100)

        _, _, heading = expected_pose(mission)
        self.assertAlmostEqual(heading, 0.0)

    def test_reverse_arc_tracks_distance_and_rightward_heading(self):
        mission = {
            "steps": [
                {
                    "type": "arc",
                    "radius_mm": -140.06,
                    "angle_deg": -45,
                }
            ]
        }

        x, y, heading = expected_pose(mission)

        chord_length = 2 * 140.06 * math.sin(math.radians(45) / 2)
        self.assertAlmostEqual((x * x + y * y) ** 0.5, chord_length, places=6)
        self.assertAlmostEqual(heading, 45.0)

    def test_control_flow_produces_possible_paths_and_uses_parallel_drive_lane(self):
        mission = {
            "steps": [
                {
                    "type": "if",
                    "condition": {
                        "sensor": "heading_deg",
                        "operator": "<",
                        "value": 20,
                    },
                    "then": [{"type": "straight", "distance_mm": 100}],
                    "else": [{"type": "turn", "angle_deg": 90}],
                },
                {
                    "type": "repeat",
                    "times": 2,
                    "steps": [{"type": "straight", "distance_mm": 50}],
                },
                {
                    "type": "parallel",
                    "branches": [
                        {
                            "resource": "drive",
                            "steps": [{"type": "straight", "distance_mm": 25}],
                        },
                        {
                            "resource": "E",
                            "steps": [
                                {
                                    "type": "attachment",
                                    "port": "E",
                                    "angle_deg": 45,
                                    "speed_deg_s": 100,
                                }
                            ],
                        },
                    ],
                },
            ]
        }

        poses = expected_poses(mission)

        self.assertEqual(len(poses), 2)
        self.assertAlmostEqual(poses[0][1], 225.0)
        self.assertAlmostEqual(poses[1][0], 125.0)
        self.assertAlmostEqual(poses[1][1], 0.0)
        self.assertAlmostEqual(poses[1][2], 90.0)

    def test_ctrl_c_stops_dry_run(self):
        mission = {
            "name": "Test",
            "steps": [{"type": "wait", "duration_ms": 100}],
        }
        with patch("mission_tester._print"), patch(
            "mission_tester.time.sleep", side_effect=KeyboardInterrupt
        ):
            result = run_dry_run(mission)

        self.assertFalse(result)

    def test_bluetooth_program_includes_runtime_and_stop_safety(self):
        root = Path(__file__).resolve().parents[1]
        mission = load_mission(root / "mission_1.json")

        with TemporaryDirectory() as directory:
            runner = _prepare_bluetooth_program(mission, directory)
            runner_source = runner.read_text(encoding="utf-8")
            mission_source = (Path(directory) / "selected_mission.py").read_text(
                encoding="utf-8"
            )

            self.assertTrue((Path(directory) / "core.py").is_file())
            self.assertTrue((Path(directory) / "config.py").is_file())
            self.assertIn("from selected_mission import run", runner_source)
            self.assertIn("hub.system.set_stop_button(Button.CENTER)", runner_source)
            self.assertIn("stop_all()", runner_source)
            self.assertIn("def run():", mission_source)

    def test_bluetooth_stop_waits_for_program_to_start_and_finish(self):
        class StatusFlag:
            USER_PROGRAM_RUNNING = 1

        updates = asyncio.Queue()
        for status in (0, 1, 0):
            updates.put_nowait(status)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_wait_for_program_stop(updates, StatusFlag))
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
