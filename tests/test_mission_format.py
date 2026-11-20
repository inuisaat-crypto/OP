import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mission_format import MissionFormatError, load_mission


class MissionFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "mission.json"
        self.mission = {
            "version": 1,
            "name": "Test",
            "color": "CYAN",
            "steps": [
                {"type": "straight", "distance_mm": 100, "speed_mm_s": 100}
            ],
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_mission(self, mission):
        self.path.write_text(json.dumps(mission), encoding="utf-8")

    def test_loads_valid_mission(self):
        self.write_mission(self.mission)
        self.assertEqual(load_mission(self.path)["name"], "Test")

    def test_loads_valid_reverse_arc(self):
        self.mission["steps"] = [
            {
                "type": "arc",
                "radius_mm": -140.06,
                "angle_deg": -45,
                "speed_mm_s": 800,
            }
        ]
        self.write_mission(self.mission)
        self.assertEqual(load_mission(self.path)["steps"][0]["type"], "arc")

    def test_accepts_valid_editor_start_pose(self):
        self.mission["start_pose"] = {
            "x_mm": 550,
            "y_mm": 120,
            "heading_deg": 0,
        }
        self.write_mission(self.mission)
        self.assertEqual(load_mission(self.path)["start_pose"]["x_mm"], 550)

    def test_rejects_start_pose_outside_field(self):
        self.mission["start_pose"] = {
            "x_mm": 1101,
            "y_mm": 120,
            "heading_deg": 0,
        }
        self.write_mission(self.mission)
        with self.assertRaises(MissionFormatError):
            load_mission(self.path)

    def test_rejects_zero_arc_radius(self):
        self.mission["steps"] = [
            {"type": "arc", "radius_mm": 0, "angle_deg": -45}
        ]
        self.write_mission(self.mission)
        with self.assertRaises(MissionFormatError):
            load_mission(self.path)

    def test_accepts_conditional_repeat_and_resource_parallel(self):
        self.mission["steps"] = [
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
                "steps": [{"type": "beep", "frequency_hz": 880, "duration_ms": 100}],
            },
            {
                "type": "parallel",
                "branches": [
                    {
                        "resource": "drive",
                        "steps": [{"type": "straight", "distance_mm": 100}],
                    },
                    {
                        "resource": "F",
                        "steps": [
                            {
                                "type": "attachment",
                                "port": "F",
                                "angle_deg": 90,
                                "speed_deg_s": 100,
                            }
                        ],
                    },
                ],
            },
        ]
        self.write_mission(self.mission)
        self.assertEqual(len(load_mission(self.path)["steps"]), 3)

    def test_rejects_parallel_lanes_that_conflict_for_drive_resource(self):
        self.mission["steps"] = [
            {
                "type": "parallel",
                "branches": [
                    {
                        "resource": "drive",
                        "steps": [{"type": "straight", "distance_mm": 100}],
                    },
                    {
                        "resource": "drive",
                        "steps": [{"type": "turn", "angle_deg": 90}],
                    },
                ],
            }
        ]
        self.write_mission(self.mission)
        with self.assertRaises(MissionFormatError):
            load_mission(self.path)

    def test_rejects_zero_distance(self):
        self.mission["steps"][0]["distance_mm"] = 0
        self.write_mission(self.mission)
        with self.assertRaises(MissionFormatError):
            load_mission(self.path)

    def test_rejects_unknown_step_type(self):
        self.mission["steps"][0] = {"type": "teleport"}
        self.write_mission(self.mission)
        with self.assertRaises(MissionFormatError):
            load_mission(self.path)

    def test_rejects_non_string_color(self):
        self.mission["color"] = []
        self.write_mission(self.mission)
        with self.assertRaises(MissionFormatError):
            load_mission(self.path)

    def test_reports_malformed_json(self):
        self.path.write_text("{", encoding="utf-8")
        with self.assertRaises(MissionFormatError):
            load_mission(self.path)


if __name__ == "__main__":
    unittest.main()
