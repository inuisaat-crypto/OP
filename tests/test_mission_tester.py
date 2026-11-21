import asyncio
import json
import math
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch

from mission_format import load_mission
from mission_tester import (
    _bluetooth_session,
    _mission_file_revision,
    _prepare_bluetooth_program,
    _run_bluetooth_mission,
    _run_bluetooth_mission_menu,
    _watch_mission_file,
    _wait_for_stop_key,
    _wait_for_program_stop,
    MissionUploadError,
    discover_missions,
    expected_pose,
    expected_poses,
    main,
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
        path = Path(__file__).resolve().parents[1] / "missions" / "mission_1.json"
        mission = load_mission(path)
        pose = mission.get("start_pose", {})

        x, y, heading = expected_pose(mission)

        self.assertAlmostEqual(x, float(pose.get("x_mm", 0)), places=6)
        self.assertAlmostEqual(y, float(pose.get("y_mm", 0)) + 30.0, places=6)
        self.assertAlmostEqual(heading, float(pose.get("heading_deg", 0)) + 180.0, places=6)

    def test_turn_to_sets_absolute_heading(self):
        mission = {
            "version": 1,
            "name": "Absolute",
            "color": "CYAN",
            "start_pose": {"x_mm": 1000, "y_mm": 570, "heading_deg": 0},
            "steps": [
                {"type": "straight", "distance_mm": 100},
                {"type": "turn_to", "heading_deg": -90},
            ],
        }

        x, y, heading = expected_pose(mission)

        self.assertAlmostEqual(x, 1000.0, places=6)
        self.assertAlmostEqual(y, 670.0, places=6)
        self.assertAlmostEqual(heading, -90.0, places=6)

    def test_wheel_turn_moves_center_around_locked_wheel(self):
        mission = {
            "version": 1,
            "name": "Pivot",
            "color": "CYAN",
            "start_pose": {"x_mm": 1000, "y_mm": 570, "heading_deg": 0},
            "steps": [{"type": "wheel_turn", "angle_deg": 90, "locked": "RIGHT"}],
        }

        x, y, heading = expected_pose(mission)

        self.assertAlmostEqual(x, 1000.0 + 165 / 2, places=6)
        self.assertAlmostEqual(y, 570.0 + 165 / 2, places=6)
        self.assertAlmostEqual(heading, 90.0, places=6)

    def test_mission_3_curves_back_to_zero_heading_while_moving(self):
        path = Path(__file__).resolve().parents[1] / "missions" / "mission_3.json"
        mission = load_mission(path)
        steps = mission["steps"]

        self.assertEqual(steps[0]["distance_mm"], 550)
        self.assertEqual(steps[1]["distance_mm"], -200)
        self.assertEqual(steps[2]["type"], "turn")
        self.assertEqual(steps[2]["angle_deg"], 60)
        self.assertEqual(steps[3]["type"], "parallel")
        drive_arc = steps[3]["branches"][0]["steps"][0]
        self.assertEqual(drive_arc["type"], "arc")
        self.assertEqual(drive_arc["radius_mm"], -350)
        self.assertEqual(drive_arc["angle_deg"], 60)
        self.assertEqual(drive_arc["speed_mm_s"], 800)
        self.assertAlmostEqual(
            abs(drive_arc["radius_mm"]) * math.radians(drive_arc["angle_deg"]),
            366.5,
            delta=0.1,
        )
        self.assertEqual(steps[4]["distance_mm"], 230)
        attachment = steps[3]["branches"][1]["steps"][0]
        self.assertEqual(attachment["port"], "F")
        self.assertEqual(attachment["angle_deg"], 100)

        _, _, heading_after_arc = expected_pose(
            dict(mission, steps=steps[:4])
        )
        self.assertAlmostEqual(heading_after_arc, 0.0)

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
        mission = load_mission(root / "missions" / "mission_1.json")

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

    def test_q_stops_keyboard_listener(self):
        class FakeKeyboard:
            def __init__(self):
                self.keys = ["x", "q"]

            def kbhit(self):
                return bool(self.keys)

            def getwch(self):
                return self.keys.pop(0)

        async def no_sleep(_delay):
            pass

        keyboard = ModuleType("msvcrt")
        fake_keyboard = FakeKeyboard()
        keyboard.kbhit = fake_keyboard.kbhit
        keyboard.getwch = fake_keyboard.getwch
        loop = asyncio.new_event_loop()
        try:
            with patch.dict("sys.modules", {"msvcrt": keyboard}), patch(
                "mission_tester.asyncio.sleep", new=no_sleep
            ):
                loop.run_until_complete(_wait_for_stop_key())
        finally:
            loop.close()

    def test_upload_error_keeps_mission_menu_open_for_retry(self):
        attempts = []
        mission = {"name": "Test mission", "color": "BLUE", "steps": []}

        async def run_with_one_upload_error(_hub, _mission):
            attempts.append(True)
            if len(attempts) == 1:
                raise MissionUploadError("GATT Protocol Error: Unlikely Error")

        loop = asyncio.new_event_loop()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "mission_1.json"
            path.write_text("test", encoding="utf-8")
            try:
                with patch("builtins.input", side_effect=["1", "2"]), patch(
                    "mission_tester.load_mission", return_value=mission
                ), patch(
                    "mission_tester._run_bluetooth_mission",
                    new=run_with_one_upload_error,
                ), patch("mission_tester._print"):
                    loop.run_until_complete(
                        _run_bluetooth_mission_menu(object(), path)
                    )
            finally:
                loop.close()

        self.assertEqual(len(attempts), 2)

    def test_restart_reloads_updated_mission_json(self):
        first_mission = {
            "version": 1,
            "name": "First version",
            "color": "BLUE",
            "steps": [{"type": "straight", "distance_mm": 100}],
        }
        updated_mission = {
            "version": 1,
            "name": "Updated version",
            "color": "GREEN",
            "steps": [{"type": "straight", "distance_mm": 200}],
        }
        run_missions = []

        async def finish_mission(_hub, mission):
            run_missions.append(mission)

        input_count = [0]

        def edit_json_while_menu_waits(_prompt):
            input_count[0] += 1
            if input_count[0] == 1:
                path.write_text(json.dumps(updated_mission), encoding="utf-8")
                time.sleep(0.6)
                return "1"
            return "2"

        loop = asyncio.new_event_loop()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "mission_1.json"
            path.write_text(json.dumps(first_mission), encoding="utf-8")
            try:
                with patch(
                    "builtins.input", side_effect=edit_json_while_menu_waits
                ), patch(
                    "mission_tester._run_bluetooth_mission", new=finish_mission
                ), patch("mission_tester._print") as print_mock:
                    loop.run_until_complete(
                        _run_bluetooth_mission_menu(object(), path)
                    )
            finally:
                loop.close()

        self.assertEqual(
            [mission["name"] for mission in run_missions],
            ["First version", "Updated version"],
        )
        self.assertTrue(
            any(
                "Mission JSON changed" in call[0][0]
                for call in print_mock.call_args_list
            )
        )

    def test_mission_file_watcher_notices_json_changes(self):
        messages = []

        with TemporaryDirectory() as directory:
            path = Path(directory) / "mission_1.json"
            path.write_text('{"name": "original"}', encoding="utf-8")
            stop_event = threading.Event()
            with patch("mission_tester._print", side_effect=messages.append):
                revision = _mission_file_revision(path)
                watcher = threading.Thread(
                    target=_watch_mission_file,
                    args=(path, revision, stop_event),
                )
                watcher.start()
                time.sleep(0.01)
                path.write_text('{"name": "updated"}', encoding="utf-8")
                watcher.join(timeout=1)
                stop_event.set()
                watcher.join(timeout=1)

        self.assertFalse(watcher.is_alive())
        self.assertTrue(any("Mission JSON changed" in message for message in messages))

    def test_gatt_upload_error_does_not_start_the_mission(self):
        class FakeBleakError(Exception):
            pass

        class FakeConnectionState:
            CONNECTED = "connected"

        class FakeSubscription:
            def __init__(self):
                self.disposed = False

            def dispose(self):
                self.disposed = True

        class FakeObservable:
            value = FakeConnectionState.CONNECTED

            def __init__(self):
                self.subscription = FakeSubscription()

            def subscribe(self, _callback):
                return self.subscription

        class FakeHub:
            def __init__(self):
                self.status_observable = FakeObservable()
                self.connection_state_observable = FakeObservable()
                self.download_calls = []
                self.run_calls = 0

            async def download(self, path):
                self.download_calls.append(path)
                raise FakeBleakError("GATT Protocol Error: Unlikely Error")

            async def run(self, **_kwargs):
                self.run_calls += 1

        bleak = ModuleType("bleak")
        bleak.__path__ = []
        bleak_exc = ModuleType("bleak.exc")
        bleak_exc.BleakError = FakeBleakError
        bleak.exc = bleak_exc
        pybricksdev = ModuleType("pybricksdev")
        pybricksdev.__path__ = []
        connections = ModuleType("pybricksdev.connections")
        connections.ConnectionState = FakeConnectionState
        pybricksdev.connections = connections
        pybricks_ble = ModuleType("pybricksdev.ble")
        pybricks_ble.__path__ = []
        pybricksdev.ble = pybricks_ble
        pybricks_ble_protocol = ModuleType("pybricksdev.ble.pybricks")
        pybricks_ble_protocol.StatusFlag = object()
        pybricks_ble.pybricks = pybricks_ble_protocol

        hub = FakeHub()
        mission = {"name": "Test", "color": "BLUE", "steps": []}
        modules = {
            "bleak": bleak,
            "bleak.exc": bleak_exc,
            "pybricksdev": pybricksdev,
            "pybricksdev.connections": connections,
            "pybricksdev.ble": pybricks_ble,
            "pybricksdev.ble.pybricks": pybricks_ble_protocol,
        }
        loop = asyncio.new_event_loop()
        try:
            with patch.dict("sys.modules", modules), patch("mission_tester._print"):
                with self.assertRaises(MissionUploadError):
                    loop.run_until_complete(_run_bluetooth_mission(hub, mission))
        finally:
            loop.close()

        self.assertEqual(len(hub.download_calls), 1)
        self.assertEqual(hub.run_calls, 0)
        self.assertTrue(hub.status_observable.subscription.disposed)
        self.assertTrue(hub.connection_state_observable.subscription.disposed)

    def test_bluetooth_session_connects_once_and_restarts_or_returns_to_list(self):
        class FakeDevice:
            name = "Test hub"
            address = "00:11:22:33:44:55"

        class FakeHub:
            def __init__(self):
                self.connect_count = 0
                self.disconnect_count = 0
                self.connected = False

            async def connect(self):
                self.connect_count += 1
                self.connected = True

            async def disconnect(self):
                self.disconnect_count += 1
                self.connected = False

        device = FakeDevice()
        hub = FakeHub()
        find_calls = []
        run_calls = []
        mission = {"name": "Test mission", "color": "BLUE", "steps": []}
        mission_path = (
            Path(__file__).resolve().parents[1] / "missions" / "mission_1.json"
        )

        async def fake_find_device(timeout):
            find_calls.append(timeout)
            return device

        async def fake_run_mission(selected_hub, selected_mission):
            run_calls.append((selected_hub.connected, selected_mission))

        pybricksdev = ModuleType("pybricksdev")
        pybricksdev.__path__ = []
        ble = ModuleType("pybricksdev.ble")
        ble.find_device = fake_find_device
        connections = ModuleType("pybricksdev.connections")
        connections.__path__ = []
        pybricks_connection = ModuleType("pybricksdev.connections.pybricks")
        pybricks_connection.PybricksHubBLE = lambda _device: hub
        pybricksdev.ble = ble
        pybricksdev.connections = connections
        connections.pybricks = pybricks_connection

        loop = asyncio.new_event_loop()
        try:
            with patch.dict(
                "sys.modules",
                {
                    "pybricksdev": pybricksdev,
                    "pybricksdev.ble": ble,
                    "pybricksdev.connections": connections,
                    "pybricksdev.connections.pybricks": pybricks_connection,
                },
            ), patch(
                "builtins.input", side_effect=["1", "1", "2", "q"]
            ) as input_mock, patch(
                "mission_tester.discover_missions", return_value=[mission_path]
            ), patch(
                "mission_tester.load_mission", return_value=mission
            ), patch(
                "mission_tester._run_bluetooth_mission", new=fake_run_mission
            ), patch("mission_tester._print"):
                result = loop.run_until_complete(_bluetooth_session())
        finally:
            loop.close()

        self.assertEqual(result, 0)
        self.assertEqual(find_calls, [20])
        self.assertEqual(hub.connect_count, 1)
        self.assertEqual(hub.disconnect_count, 1)
        self.assertEqual(len(run_calls), 2)
        self.assertTrue(all(connected for connected, _ in run_calls))
        self.assertTrue(all(selected is mission for _, selected in run_calls))
        self.assertEqual(input_mock.call_count, 4)

    def test_tester_connects_by_default_and_keeps_offline_mode_explicit(self):
        with patch("mission_tester.sys.argv", ["mission_tester.py"]), patch(
            "mission_tester._run_bluetooth_mode", return_value=0
        ) as bluetooth_mode, patch(
            "mission_tester._run_offline_mode", return_value=0
        ) as offline_mode:
            self.assertEqual(main(), 0)
        bluetooth_mode.assert_called_once_with()
        offline_mode.assert_not_called()

        with patch(
            "mission_tester.sys.argv", ["mission_tester.py", "--offline"]
        ), patch("mission_tester._run_offline_mode", return_value=0) as offline_mode:
            self.assertEqual(main(), 0)
        offline_mode.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
