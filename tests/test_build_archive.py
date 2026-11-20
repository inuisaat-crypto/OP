import unittest
import zipfile

from build_archive import ARCHIVE_FILES, ROOT, _render_mission, build_archive
from mission_format import validate_mission


class BuildArchiveTests(unittest.TestCase):
    def test_json_steps_are_rendered_as_pybricks_calls(self):
        mission = {
            "version": 1,
            "name": "Generated",
            "color": "CYAN",
            "steps": [
                {"type": "straight", "distance_mm": 200, "speed_mm_s": 100},
                {"type": "straight", "distance_mm": -25},
                {"type": "turn", "angle_deg": 90, "rate_deg_s": 60},
                {"type": "turn", "angle_deg": -90},
                {
                    "type": "arc",
                    "radius_mm": -140.06,
                    "angle_deg": -45,
                    "speed_mm_s": 800,
                },
                {
                    "type": "attachment",
                    "port": "E",
                    "angle_deg": 45,
                    "speed_deg_s": 90,
                },
                {
                    "type": "attachment",
                    "port": "F",
                    "angle_deg": -30,
                    "speed_deg_s": 80,
                },
                {"type": "wait", "duration_ms": 300},
                {"type": "beep", "frequency_hz": 880, "duration_ms": 150},
            ],
        }
        source = _render_mission("mission_generated", validate_mission(mission))
        source = source.decode("utf-8")

        for call in (
            "straight(200, speed=100)",
            "straight(-25)",
            "turn(90, rate=60)",
            "turn(-90)",
            "arc(-140.06, -45, speed=800)",
            "att_run(att_left, 90, 45)",
            "att_run(att_right, 80, -30)",
            "wait(300)",
            "hub.speaker.beep(880, 150)",
        ):
            self.assertIn(call, source)
        compile(source, "mission_generated.py", "exec")

    def test_control_flow_and_parallel_lanes_compile_to_python(self):
        mission = {
            "version": 1,
            "name": "Control",
            "color": "CYAN",
            "steps": [
                {
                    "type": "if",
                    "condition": {
                        "sensor": "heading_deg",
                        "operator": "<",
                        "value": 45,
                    },
                    "then": [{"type": "straight", "distance_mm": 100}],
                    "else": [{"type": "turn", "angle_deg": 90}],
                },
                {
                    "type": "repeat",
                    "times": 2,
                    "steps": [{"type": "wait", "duration_ms": 10}],
                },
                {
                    "type": "parallel",
                    "branches": [
                        {
                            "resource": "drive",
                            "steps": [{"type": "straight", "distance_mm": 200}],
                        },
                        {
                            "resource": "F",
                            "steps": [
                                {
                                    "type": "attachment",
                                    "port": "F",
                                    "angle_deg": 100,
                                    "speed_deg_s": 800,
                                }
                            ],
                        },
                    ],
                },
            ],
        }
        source = _render_mission("mission_control", validate_mission(mission))
        source = source.decode("utf-8")

        self.assertIn("if hub.imu.heading() < 45:", source)
        self.assertIn("for _ in range(2):", source)
        self.assertIn("att_run(att_right, 800, 100, wait=False)", source)
        self.assertIn("straight(200)", source)
        self.assertIn("att_wait(att_right)", source)
        compile(source, "mission_control.py", "exec")

    def test_archive_compiles_and_registers_every_json_mission(self):
        archive_path = build_archive()
        with zipfile.ZipFile(str(archive_path)) as archive:
            names = set(archive.namelist())
            catalog = archive.read("mission_catalog.py").decode("utf-8")
            compile(catalog, "mission_catalog.py", "exec")

            mission_files = sorted(ROOT.glob("mission_*.json"))
            expected_missions = {path.stem + ".py" for path in mission_files}
            for path in mission_files:
                module_name = path.stem
                self.assertIn(
                    "('{}', _{}_name, _{}_run, _{}_color),".format(
                        module_name, module_name, module_name, module_name
                    ),
                    catalog,
                )
                generated_source = archive.read(module_name + ".py").decode("utf-8")
                compile(generated_source, module_name + ".py", "exec")
                self.assertNotIn(path.name, names)

        expected = {target for _, target in ARCHIVE_FILES} | expected_missions
        self.assertEqual(names, expected)
        self.assertIn("main.py", names)
        self.assertIn("mission_catalog.py", names)
        self.assertIn("system_check.py", names)
        self.assertIn("mission_3.py", names)
        self.assertTrue(all(name.endswith(".py") for name in names))
        self.assertTrue(all("/" not in name for name in names))


if __name__ == "__main__":
    unittest.main()
