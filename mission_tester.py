"""Terminal validator and dry-run preview for JSON missions."""

import asyncio
import hashlib
import math
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

from mission_format import MissionFormatError, load_mission


ROOT = Path(__file__).resolve().parent
MISSIONS_DIR = ROOT / "missions"
AXLE_TRACK_MM = 165
STEP_DELAY_SECONDS = 0.4
SIMULATION_PATH_LIMIT = 16
SIMULATION_STEP_LIMIT = 10000
MISSION_WATCH_INTERVAL_SECONDS = 0.25


class MissionUploadError(RuntimeError):
    pass


def _print(message):
    text = str(message)
    encoding = getattr(sys.stdout, "encoding", None)
    if encoding:
        try:
            text.encode(encoding)
        except UnicodeEncodeError:
            text = text.encode(encoding, "backslashreplace").decode(encoding)
    sys.stdout.write(text + "\n")


def discover_missions(directory=None):
    folder = Path(directory) if directory is not None else MISSIONS_DIR
    return sorted(
        folder.glob("mission_*.json"),
        key=lambda path: path.name.lower(),
    )


def describe_step(step):
    kind = step["type"]
    if kind == "straight":
        text = "Straight {} mm".format(step["distance_mm"])
        if "speed_mm_s" in step:
            text += " at {} mm/s".format(step["speed_mm_s"])
        return text
    if kind == "turn":
        text = "Turn {} deg".format(step["angle_deg"])
        if "rate_deg_s" in step:
            text += " at {} deg/s".format(step["rate_deg_s"])
        return text
    if kind == "arc":
        text = "Arc radius {} mm, angle {} deg".format(
            step["radius_mm"], step["angle_deg"]
        )
        if "speed_mm_s" in step:
            text += " at {} mm/s".format(step["speed_mm_s"])
        return text
    if kind == "attachment":
        return "Attachment {}: {} deg at {} deg/s".format(
            step["port"], step["angle_deg"], step["speed_deg_s"]
        )
    if kind == "wait":
        return "Wait {} ms".format(step["duration_ms"])
    if kind == "if":
        condition = step["condition"]
        sensor = condition["sensor"]
        if sensor == "attachment_angle_deg":
            sensor += "({})".format(condition["port"])
        return "If {} {} {} (then {}, else {})".format(
            sensor,
            condition["operator"],
            condition["value"],
            len(step["then"]),
            len(step.get("else", [])),
        )
    if kind == "repeat":
        return "Repeat {} times ({} commands)".format(
            step["times"], len(step["steps"])
        )
    if kind == "parallel":
        return "Parallel: {}".format(
            ", ".join(
                "{} ({} commands)".format(branch["resource"], len(branch["steps"]))
                for branch in step["branches"]
            )
        )
    if kind == "beep":
        return "Beep {} Hz for {} ms".format(
            step["frequency_hz"], step["duration_ms"]
        )
    if kind == "turn_to":
        text = "Turn to {} deg".format(step["heading_deg"])
        if "rate_deg_s" in step:
            text += " at {} deg/s".format(step["rate_deg_s"])
        return text
    if kind == "wheel_turn":
        text = "Pivot turn {} deg on {}".format(
            step["angle_deg"], step["locked"].lower()
        )
        if "rate_deg_s" in step:
            text += " at {} deg/s".format(step["rate_deg_s"])
        return text
    if kind == "wall_square":
        return "Wall square to {} deg ({} ms)".format(
            step["heading_deg"], step.get("duration_ms", 800)
        )
    if kind == "set_speed":
        return "Speed profile {}".format(step["profile"])
    if kind == "set_heading":
        return "Set heading reference {} deg".format(step["heading_deg"])
    if kind == "rush":
        return "Rush mode {}".format("on" if step["enabled"] else "off")
    if kind == "stop":
        return "Stop: {}".format(step["scope"])
    if kind == "att_until_stalled":
        return "Attachment {} until stalled at {} deg/s".format(
            step["port"], step["speed_deg_s"]
        )
    if kind == "set_att_accel":
        return "Attachment acceleration {} deg/s2".format(step["accel_deg_s2"])
    if kind == "battery_check":
        return "Battery check"
    if kind == "reset_start":
        return "Reset start state"
    if kind == "log":
        return "Log: {}".format(step["message"])
    return "Step {!r}".format(kind)


def advance_pose(x, y, heading, step):
    if step["type"] == "straight":
        angle = math.radians(heading)
        distance = step["distance_mm"]
        x += distance * math.sin(angle)
        y += distance * math.cos(angle)
    elif step["type"] == "turn":
        heading += step["angle_deg"]
    elif step["type"] == "turn_to":
        heading = step["heading_deg"]
    elif step["type"] == "wheel_turn":
        delta = step["angle_deg"]
        half = AXLE_TRACK_MM / 2
        offset = -half if step["locked"] == "RIGHT" else half
        start = math.radians(heading)
        ox = offset * math.cos(start)
        oy = -offset * math.sin(start)
        cos_d = math.cos(math.radians(delta))
        sin_d = math.sin(math.radians(delta))
        nx = ox * cos_d + oy * sin_d
        ny = -ox * sin_d + oy * cos_d
        x += nx - ox
        y += ny - oy
        heading += delta
    elif step["type"] == "arc":
        radius = step["radius_mm"]
        start = math.radians(heading)
        heading += step["angle_deg"] if radius > 0 else -step["angle_deg"]
        end = math.radians(heading)
        x += radius * (math.cos(start) - math.cos(end))
        y += radius * (math.sin(end) - math.sin(start))
    return x, y, heading


def expected_pose(mission):
    return expected_poses(mission)[0]


def _initial_pose(mission):
    pose = mission.get("start_pose", {})
    return (
        float(pose.get("x_mm", 0)),
        float(pose.get("y_mm", 0)),
        float(pose.get("heading_deg", 0)),
    )


def _simulate_steps(states, steps, budget):
    current = states
    for step in steps:
        if budget[0] <= 0:
            break
        budget[0] -= 1
        kind = step["type"]
        if kind == "if":
            alternatives = []
            for state in current:
                alternatives.extend(_simulate_steps([state], step["then"], budget))
                alternatives.extend(
                    _simulate_steps([state], step.get("else", []), budget)
                )
            current = alternatives[:SIMULATION_PATH_LIMIT] or current
        elif kind == "repeat":
            for _ in range(step["times"]):
                current = _simulate_steps(current, step["steps"], budget)
                if budget[0] <= 0:
                    break
        elif kind == "parallel":
            drive = next(
                (
                    branch
                    for branch in step["branches"]
                    if branch["resource"] == "drive"
                ),
                None,
            )
            if drive:
                current = _simulate_steps(current, drive["steps"], budget)
        else:
            current = [
                advance_pose(state[0], state[1], state[2], step)
                for state in current
            ]
        current = current[:SIMULATION_PATH_LIMIT]
    return current


def expected_poses(mission):
    budget = [SIMULATION_STEP_LIMIT]
    return _simulate_steps([_initial_pose(mission)], mission["steps"], budget)


def _print_step_tree(steps, indent=0):
    prefix = "  " * indent
    for step in steps:
        _print(prefix + describe_step(step))
        if step["type"] == "if":
            _print(prefix + "  Then branch:")
            _print_step_tree(step["then"], indent + 2)
            if "else" in step:
                _print(prefix + "  Else branch:")
                _print_step_tree(step["else"], indent + 2)
        elif step["type"] == "repeat":
            _print_step_tree(step["steps"], indent + 1)
        elif step["type"] == "parallel":
            for branch in step["branches"]:
                _print(prefix + "  {} lane:".format(branch["resource"]))
                _print_step_tree(branch["steps"], indent + 2)


def run_dry_run(mission, step_delay=STEP_DELAY_SECONDS):
    states = [_initial_pose(mission)]
    budget = [SIMULATION_STEP_LIMIT]
    _print(
        "DRY RUN only: no robot or sensors are connected. "
        "Conditional blocks show both possible branches. Press Ctrl+C to stop."
    )

    try:
        _print_step_tree(mission["steps"])
        for index, step in enumerate(mission["steps"]):
            states = _simulate_steps(states, [step], budget)
            for path_index, (x, y, heading) in enumerate(states):
                _print(
                    "  Route {} after top-level step {}: "
                    "x={:.1f} mm, y={:.1f} mm, heading={:.1f} deg".format(
                        path_index + 1, index + 1, x, y, heading
                    )
                )
            time.sleep(step_delay)
    except KeyboardInterrupt:
        _print("Dry run stopped.")
        return False

    if budget[0] <= 0:
        _print("Preview truncated after {} simulated commands.".format(
            SIMULATION_STEP_LIMIT
        ))

    if len(states) == 1:
        x, y, heading = states[0]
        _print(
            "Dry run complete. Final expected pose: "
            "x={:.1f} mm, y={:.1f} mm, heading={:.1f} deg".format(x, y, heading)
        )
    else:
        _print("Dry run complete. {} possible final routes.".format(len(states)))
    return True


def _show_mission(mission):
    _print("Mission: {}".format(mission["name"]))
    _print("Color: {}".format(mission["color"]))
    for index, step in enumerate(mission["steps"]):
        _print("  {}. {}".format(index + 1, describe_step(step)))


def _prepare_bluetooth_program(mission, directory):
    from build_archive import _render_mission

    directory = Path(directory)
    shutil.copyfile(ROOT / "pybricks_runtime" / "config.py", directory / "config.py")
    shutil.copyfile(ROOT / "pybricks_runtime" / "core.py", directory / "core.py")
    (directory / "selected_mission.py").write_bytes(
        _render_mission("selected_mission", mission)
    )
    runner = directory / "mission_runner.py"
    runner.write_text(
        "from core import hub, left_motor, right_motor, stop_all\n"
        "from pybricks.parameters import Button\n"
        "from selected_mission import run\n"
        "\n"
        "hub.system.set_stop_button(Button.CENTER)\n"
        "try:\n"
        "    run()\n"
        "finally:\n"
        "    try:\n"
        "        stop_all()\n"
        "    finally:\n"
        "        left_motor.stop()\n"
        "        right_motor.stop()\n"
        "        hub.system.set_stop_button(None)\n",
        encoding="utf-8",
    )
    return runner


async def _wait_for_program_stop(status_updates, status_flag):
    running_seen = False
    last_running = None

    while True:
        timeout = None if running_seen else 1.0
        try:
            status = await asyncio.wait_for(status_updates.get(), timeout)
        except asyncio.TimeoutError:
            return

        running = bool(status & status_flag.USER_PROGRAM_RUNNING)
        if running == last_running:
            continue
        last_running = running
        if running:
            running_seen = True
        elif running_seen:
            return


async def _wait_for_disconnect(connection_updates, connection_state):
    while True:
        state = await connection_updates.get()
        if state == connection_state.DISCONNECTED:
            return


async def _wait_for_stop_key():
    import msvcrt

    while True:
        if msvcrt.kbhit():
            key = msvcrt.getwch()
            if key.lower() == "q" or key == "\x1b":
                return
            if key in ("\x00", "\xe0"):
                msvcrt.getwch()
        await asyncio.sleep(0.05)


async def _run_bluetooth_mission(hub, mission):
    from bleak.exc import BleakError
    from pybricksdev.connections import ConnectionState
    from pybricksdev.ble.pybricks import StatusFlag

    with tempfile.TemporaryDirectory(prefix="op_mission_") as temporary_directory:
        runner = _prepare_bluetooth_program(mission, temporary_directory)
        status_updates = asyncio.Queue()
        connection_updates = asyncio.Queue()
        status_subscription = hub.status_observable.subscribe(
            status_updates.put_nowait
        )
        connection_subscription = hub.connection_state_observable.subscribe(
            connection_updates.put_nowait
        )
        tasks = []

        try:
            _print("Uploading mission to the hub...")
            try:
                await hub.download(str(runner))
            except (BleakError, OSError) as error:
                if (
                    hub.connection_state_observable.value
                    != ConnectionState.CONNECTED
                ):
                    raise RuntimeError(
                        "Bluetooth disconnected during upload. The mission "
                        "was not started; restart the tester to reconnect."
                    ) from error
                raise MissionUploadError(str(error)) from error

            await hub.run(wait=False, print_output=True, line_handler=True)
            _print("Mission running. Press Q (or Esc) to stop.")
            completion_task = asyncio.ensure_future(
                _wait_for_program_stop(status_updates, StatusFlag)
            )
            stop_key_task = asyncio.ensure_future(_wait_for_stop_key())
            disconnect_task = asyncio.ensure_future(
                _wait_for_disconnect(connection_updates, ConnectionState)
            )
            tasks.extend((completion_task, stop_key_task, disconnect_task))

            done, _ = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            if completion_task in done:
                _print("Mission finished.")
            elif disconnect_task in done:
                raise RuntimeError(
                    "Bluetooth disconnected. If the robot is still moving, "
                    "press the hub's CENTER button."
                )
            else:
                _print("Sending stop command...")
                try:
                    await hub.stop_user_program()
                except (BleakError, OSError, RuntimeError) as error:
                    raise RuntimeError(
                        "Could not send the Q stop command. Press the hub's "
                        "CENTER button if the robot is still moving: {}".format(
                            error
                        )
                    )
                stopped, _ = await asyncio.wait(
                    (completion_task, disconnect_task),
                    timeout=5.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if disconnect_task in stopped and completion_task not in stopped:
                    raise RuntimeError(
                        "Bluetooth disconnected before the stop was confirmed. "
                        "Press the hub's CENTER button if the robot is still moving."
                    )
                if completion_task not in stopped:
                    raise RuntimeError(
                        "The hub did not confirm the stop. Press its CENTER button."
                    )
                _print("Mission stopped.")
        finally:
            status_subscription.dispose()
            connection_subscription.dispose()
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


def _mission_file_revision(path):
    return hashlib.sha256(Path(path).read_bytes()).digest()


def _watch_mission_file(path, initial_revision, stop_event):
    candidate_revision = None
    reported_read_error = None
    while not stop_event.wait(MISSION_WATCH_INTERVAL_SECONDS):
        try:
            revision = _mission_file_revision(path)
        except OSError as error:
            message = str(error)
            if message != reported_read_error:
                _print("Could not monitor mission JSON changes: {}".format(error))
                reported_read_error = message
            continue
        reported_read_error = None
        if revision == initial_revision:
            candidate_revision = None
        elif revision == candidate_revision:
            _print(
                "Mission JSON changed. The current run will continue; "
                "choose 1 after it stops to load the updated file."
            )
            return
        else:
            candidate_revision = revision


async def _run_bluetooth_mission_menu(hub, mission_path):
    previous_revision = None
    while True:
        try:
            mission = load_mission(mission_path)
            revision = _mission_file_revision(mission_path)
        except (OSError, UnicodeError, MissionFormatError) as error:
            _print("Mission file error: {}".format(error))
            return

        if previous_revision is None:
            _show_mission(mission)
            _print("The robot will move. Clear the area before selecting a mission.")
        elif revision != previous_revision:
            _print("Updated mission JSON loaded:")
            _show_mission(mission)

        previous_revision = revision
        stop_watcher = threading.Event()
        watcher_thread = threading.Thread(
            target=_watch_mission_file,
            args=(mission_path, revision, stop_watcher),
            name="mission-json-watcher",
            daemon=True,
        )
        watcher_thread.start()
        try:
            try:
                await _run_bluetooth_mission(hub, mission)
            except MissionUploadError as error:
                _print(
                    "Mission upload failed; the mission was not started: {}".format(
                        error
                    )
                )
                _print("  1. Retry upload")
            else:
                _print("Mission menu:")
                _print("  1. Restart this mission")
            _print("  2. Return to the mission list")
            while True:
                choice = input("Select 1 or 2: ").strip()
                if choice == "1":
                    break
                if choice == "2":
                    return
                _print("Invalid selection.")
        finally:
            stop_watcher.set()
            watcher_thread.join(timeout=1.0)


async def _bluetooth_session():
    from pybricksdev.ble import find_device
    from pybricksdev.connections.pybricks import PybricksHubBLE

    _print("Searching for a Pybricks hub over Bluetooth...")
    device = await find_device(timeout=20)
    hub = PybricksHubBLE(device)
    await hub.connect()

    try:
        _print("Connected to {}.".format(device.name or device.address))
        while True:
            missions = discover_missions()
            if not missions:
                _print("No mission_*.json files found in missions/.")
                return 0

            _print("Available JSON missions:")
            for index, path in enumerate(missions):
                _print("  {}. {}".format(index + 1, path.name))
            choice = input(
                "Select a mission (it starts immediately), or q to disconnect: "
            ).strip().lower()
            if choice == "q":
                return 0
            if not choice.isdigit() or not (1 <= int(choice) <= len(missions)):
                _print("Invalid selection.")
                continue

            path = missions[int(choice) - 1]
            await _run_bluetooth_mission_menu(hub, path)
    finally:
        await hub.disconnect()


def _run_bluetooth_mode():
    if sys.version_info < (3, 10):
        _print(
            "Bluetooth mode requires Python 3.10 or newer. Install the optional "
            "dependency with 'py -3 -m pip install -r "
            "requirements-mission-tester.txt', then run 'py -3 mission_tester.py'."
        )
        return 1
    if sys.platform != "win32":
        _print("Mission stop-key support is currently available only on Windows.")
        return 1

    try:
        from bleak.exc import BleakError

        return asyncio.run(_bluetooth_session())
    except ImportError as error:
        _print(
            "Bluetooth dependencies are unavailable: {}. Install them with "
            "'py -3 -m pip install -r requirements-mission-tester.txt'.".format(
                error
            )
        )
        return 1
    except asyncio.TimeoutError:
        _print("Bluetooth scan timed out. Check that the hub is on and advertising.")
        return 1
    except (BleakError, OSError, RuntimeError, ValueError) as error:
        _print("Bluetooth mission tester failed: {}".format(error))
        return 1


def _run_offline_mode():
    while True:
        missions = discover_missions()
        if not missions:
            _print("No mission_*.json files found in missions/.")
            return 1

        _print("JSON mission tester (offline dry-run)")
        for index, path in enumerate(missions):
            _print("  {}. {}".format(index + 1, path.name))
        choice = input("Select a number, or q to quit: ").strip().lower()
        if choice == "q":
            return 0
        if not choice.isdigit() or not (1 <= int(choice) <= len(missions)):
            _print("Invalid selection.")
            continue

        path = missions[int(choice) - 1]
        try:
            mission = load_mission(path)
        except (OSError, UnicodeError, MissionFormatError) as error:
            _print("Mission error: {}".format(error))
            continue

        _show_mission(mission)
        choice = input("Press Enter to run dry-run, or q to cancel: ").strip().lower()
        if choice != "q":
            run_dry_run(mission)


def main():
    if sys.argv[1:] == ["--offline"]:
        return _run_offline_mode()
    if len(sys.argv) > 1:
        _print("Usage: mission_tester.py [--offline]")
        return 2
    return _run_bluetooth_mode()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _print("Tester stopped.")
        sys.exit(130)
