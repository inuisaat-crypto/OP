import asyncio
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch

from build_archive import (
    ARCHIVE_FILES,
    MISSIONS_DIR,
    _extract_archive,
    _install_archive_async,
    _render_mission,
    _wait_for_program_start,
    build_archive,
    main,
)
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
            "beep(880, 150)",
        ):
            self.assertIn(call, source)
        compile(source, "mission_generated.py", "exec")

    def test_extended_commands_render_as_pybricks_calls(self):
        mission = {
            "version": 1,
            "name": "Extended",
            "color": "CYAN",
            "steps": [
                {"type": "turn_to", "heading_deg": 0, "rate_deg_s": 90},
                {"type": "wheel_turn", "angle_deg": 45, "locked": "RIGHT", "rate_deg_s": 120},
                {"type": "wall_square", "heading_deg": 0, "duty": 35, "duration_ms": 800},
                {"type": "set_speed", "profile": "SLOW"},
                {"type": "set_heading", "heading_deg": 0},
                {"type": "rush", "enabled": True},
                {"type": "stop", "scope": "drive"},
                {"type": "stop", "scope": "all"},
                {"type": "stop", "scope": "release"},
                {
                    "type": "att_until_stalled",
                    "port": "E",
                    "speed_deg_s": 400,
                    "duty_limit": 80,
                },
                {"type": "set_att_accel", "accel_deg_s2": 600},
                {"type": "log", "message": "точка 1"},
                {"type": "battery_check"},
                {"type": "reset_start"},
            ],
        }
        source = _render_mission("mission_extended", validate_mission(mission))
        source = source.decode("utf-8")

        for call in (
            "turn_to(0, rate=90)",
            "wheel_turn(45, locked='right', rate=120)",
            "wall_square(0, duty=35, duration=800)",
            "set_speed('SLOW')",
            "set_heading(0)",
            "rush(True)",
            "stop_drive()",
            "stop_all()",
            "release_drive()",
            "att_run_until_stalled(att_left, 400, duty_limit=80)",
            "set_att_accel(600)",
            "log('точка 1')",
            "battery_check()",
            "reset_start()",
        ):
            self.assertIn(call, source)
        compile(source, "mission_extended.py", "exec")

    def test_generated_mission_imports_only_used_names(self):
        mission = {
            "version": 1,
            "name": "Lean",
            "color": "CYAN",
            "steps": [
                {"type": "straight", "distance_mm": 100},
                {"type": "beep", "frequency_hz": 880, "duration_ms": 100},
            ],
        }
        source = _render_mission("mission_lean", validate_mission(mission)).decode("utf-8")

        core_imports = [
            line for line in source.splitlines() if line.startswith("from core import")
        ]
        self.assertEqual(core_imports, ["from core import beep, straight"])
        self.assertNotIn("from pybricks.tools import wait", source)
        self.assertNotIn("from pybricks.parameters import Stop", source)
        compile(source, "mission_lean.py", "exec")

    def test_through_flag_renders_stop_none_and_adds_stop_import(self):
        mission = {
            "version": 1,
            "name": "Through",
            "color": "CYAN",
            "steps": [
                {"type": "straight", "distance_mm": 400, "through": True},
                {"type": "turn", "angle_deg": 90, "through": True},
                {"type": "straight", "distance_mm": 100},
            ],
        }
        source = _render_mission("mission_through", validate_mission(mission)).decode("utf-8")

        self.assertIn("straight(400, then=Stop.NONE)", source)
        self.assertIn("turn(90, then=Stop.NONE)", source)
        self.assertIn("from pybricks.parameters import Stop", source)
        self.assertIn("straight(100)", source)
        self.assertNotIn("rush(", source)
        compile(source, "mission_through.py", "exec")

    def test_generated_mission_never_enables_rush_on_its_own(self):
        mission = {
            "version": 1,
            "name": "Plain",
            "color": "CYAN",
            "steps": [{"type": "straight", "distance_mm": 50}],
        }
        source = _render_mission("mission_plain", validate_mission(mission)).decode("utf-8")

        self.assertNotIn("rush(", source)

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

            mission_files = sorted(MISSIONS_DIR.glob("mission_*.json"))
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

    def test_installer_extracts_only_python_files_and_finds_main(self):
        archive_path = build_archive()
        with TemporaryDirectory() as directory:
            main_path = _extract_archive(archive_path, directory)
            extracted = {path.name for path in Path(directory).iterdir()}

        expected = {target for _, target in ARCHIVE_FILES} | {
            path.stem + ".py" for path in MISSIONS_DIR.glob("mission_*.json")
        }
        self.assertEqual(main_path.name, "main.py")
        self.assertEqual(extracted, expected)

    def test_cli_builds_archive_by_default(self):
        with patch("builtins.print"), patch(
            "build_archive.build_archive", return_value=Path("fake.zip")
        ) as build:
            self.assertEqual(main([]), 0)

        build.assert_called_once_with()

    def test_cli_installs_archive_without_running_when_requested(self):
        with patch("builtins.print"), patch(
            "build_archive.build_archive", return_value=Path("fake.zip")
        ), patch("build_archive.install_archive", return_value=0) as install:
            self.assertEqual(main(["--install", "--no-run"]), 0)

        install.assert_called_once_with(Path("fake.zip"), run_program=False)

    def test_cli_installs_and_runs_by_default(self):
        with patch("builtins.print"), patch(
            "build_archive.build_archive", return_value=Path("fake.zip")
        ), patch("build_archive.install_archive", return_value=0) as install:
            self.assertEqual(main(["--install"]), 0)

        install.assert_called_once_with(Path("fake.zip"), run_program=True)

    def test_cli_rejects_no_run_without_install_and_unknown_flags(self):
        with patch("builtins.print"):
            self.assertEqual(main(["--no-run"]), 2)
            self.assertEqual(main(["--wat"]), 2)

    def test_wait_for_program_start_uses_hub_status(self):
        class StatusFlag:
            USER_PROGRAM_RUNNING = 1

        class Subscription:
            def dispose(self):
                pass

        class Observable:
            def __init__(self, status):
                self.status = status

            def subscribe(self, callback):
                callback(self.status)
                return Subscription()

        class Hub:
            def __init__(self, status):
                self.status_observable = Observable(status)

        running_hub = Hub(StatusFlag.USER_PROGRAM_RUNNING)
        idle_hub = Hub(0)

        self.assertTrue(
            asyncio.run(_wait_for_program_start(running_hub, StatusFlag, timeout=0.1))
        )
        self.assertFalse(
            asyncio.run(_wait_for_program_start(idle_hub, StatusFlag, timeout=0.01))
        )

    def test_installer_downloads_and_starts_archive(self):
        archive_path = build_archive()
        events = []
        running = [False]

        class StatusFlag:
            USER_PROGRAM_RUNNING = 1

        class Subscription:
            def dispose(self):
                pass

        class Observable:
            def subscribe(self, callback):
                if running[0]:
                    callback(StatusFlag.USER_PROGRAM_RUNNING)
                return Subscription()

        class Device:
            name = "Test hub"
            address = "00:11:22:33:44:55"

        class FakeHub:
            def __init__(self, device):
                self.device = device
                self.status_observable = Observable()

            async def connect(self):
                events.append("connect")

            async def download(self, path):
                events.append(("download", Path(path).is_file()))

            async def run(self, **kwargs):
                events.append(("run", kwargs))
                running[0] = True

            async def disconnect(self):
                events.append("disconnect")

        async def find_device(timeout):
            events.append(("scan", timeout))
            return Device()

        pybricksdev = ModuleType("pybricksdev")
        pybricksdev.__path__ = []
        ble = ModuleType("pybricksdev.ble")
        ble.find_device = find_device
        ble_pybricks = ModuleType("pybricksdev.ble.pybricks")
        ble_pybricks.StatusFlag = StatusFlag
        connections = ModuleType("pybricksdev.connections")
        connections.__path__ = []
        connection = ModuleType("pybricksdev.connections.pybricks")
        connection.PybricksHubBLE = FakeHub
        pybricksdev.ble = ble
        pybricksdev.connections = connections
        modules = {
            "pybricksdev": pybricksdev,
            "pybricksdev.ble": ble,
            "pybricksdev.ble.pybricks": ble_pybricks,
            "pybricksdev.connections": connections,
            "pybricksdev.connections.pybricks": connection,
        }

        with patch.dict(sys.modules, modules), patch("builtins.print"):
            result = asyncio.run(_install_archive_async(archive_path, True, 0.1))

        self.assertEqual(result, 0)
        self.assertEqual(events[0], ("scan", 0.1))
        self.assertEqual(events[1], "connect")
        self.assertEqual(events[2][0], "download")
        self.assertTrue(events[2][1])
        self.assertEqual(events[3][0], "run")
        self.assertFalse(events[3][1]["wait"])
        self.assertEqual(events[4], "disconnect")


if __name__ == "__main__":
    unittest.main()
