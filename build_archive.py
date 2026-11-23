import ast
import asyncio
import keyword
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from mission_format import load_mission


ROOT = Path(__file__).resolve().parent
MISSIONS_DIR = ROOT / "missions"
ARCHIVE_PATH = MISSIONS_DIR / "OP_pybricks_project.zip"

# Всё, что сгенерированная миссия может взять из core. Импорт пишется только на
# реально использованные имена: у хаба мало RAM, и лишние имена в модуле миссии
# остаются в памяти на всё время работы программы.
CORE_EXPORTS = (
    "arc",
    "att_left",
    "att_right",
    "att_run",
    "att_run_until_stalled",
    "att_wait",
    "battery_check",
    "beep",
    "hub",
    "log",
    "release_drive",
    "reset_start",
    "rush",
    "set_att_accel",
    "set_heading",
    "set_speed",
    "stop_all",
    "stop_drive",
    "straight",
    "turn",
    "turn_to",
    "wall_square",
    "wheel_turn",
)
ARCHIVE_FILES = (
    ("pybricks_runtime/config.py", "config.py"),
    ("pybricks_runtime/core.py", "core.py"),
    ("pybricks_runtime/main.py", "main.py"),
    ("pybricks_runtime/menu.py", "menu.py"),
    ("pybricks_runtime/mission_recording.py", "mission_recording.py"),
    ("mission_catalog.py", "mission_catalog.py"),
    ("system_check.py", "system_check.py"),
)


def _load_json_missions():
    missions = {}
    for path in sorted(MISSIONS_DIR.glob("mission_*.json")):
        module_name = path.stem
        if not module_name.isidentifier() or keyword.iskeyword(module_name):
            raise ValueError(
                "Mission filename must form a Python module name: {}".format(
                    path.name
                )
            )
        missions[module_name] = load_mission(str(path))
    return missions


def _render_mission(module_name, mission):
    body = []
    _render_steps(body, mission["steps"], 1)
    if not body:
        body = ["    pass"]
    body_text = "\n".join(body)

    imports = []
    core_names = [
        name for name in CORE_EXPORTS if re.search(r"\b" + name + r"\b", body_text)
    ]
    if core_names:
        imports.append("from core import " + ", ".join(sorted(core_names)))
    if "Stop." in body_text:
        imports.append("from pybricks.parameters import Stop")
    if re.search(r"\bwait\(", body_text):
        imports.append("from pybricks.tools import wait")

    lines = [
        "# Generated from {}.json by build_archive.py.".format(module_name),
        "# Импортируются только те имена, которые миссия действительно вызывает.",
    ]
    lines.extend(imports)
    lines.extend(
        [
            "",
            "NAME = {!r}".format(mission["name"]),
            "COLOR = {!r}".format(mission["color"]),
            "",
            "def run():",
        ]
    )
    lines.extend(body)
    return ("\n".join(lines) + "\n").encode("utf-8")


def _condition_expression(condition):
    sensors = {
        "heading_deg": "hub.imu.heading()",
        "battery_mv": "hub.battery.voltage()",
    }
    if condition["sensor"] == "attachment_angle_deg":
        motor = "att_left" if condition["port"] == "E" else "att_right"
        sensor = "{}.angle()".format(motor)
    else:
        sensor = sensors[condition["sensor"]]
    return "{} {} {!r}".format(
        sensor, condition["operator"], condition["value"]
    )


def _render_steps(lines, steps, indent):
    prefix = "    " * indent
    for step in steps:
        kind = step["type"]
        if kind == "straight":
            args = [repr(step["distance_mm"])]
            if "speed_mm_s" in step:
                args.append("speed={!r}".format(step["speed_mm_s"]))
            if step.get("through"):
                args.append("then=Stop.NONE")
            lines.append("{}straight({})".format(prefix, ", ".join(args)))
        elif kind == "turn":
            args = [repr(step["angle_deg"])]
            if "rate_deg_s" in step:
                args.append("rate={!r}".format(step["rate_deg_s"]))
            if step.get("through"):
                args.append("then=Stop.NONE")
            lines.append("{}turn({})".format(prefix, ", ".join(args)))
        elif kind == "arc":
            args = [repr(step["radius_mm"]), repr(step["angle_deg"])]
            if "speed_mm_s" in step:
                args.append("speed={!r}".format(step["speed_mm_s"]))
            if step.get("through"):
                args.append("then=Stop.NONE")
            lines.append("{}arc({})".format(prefix, ", ".join(args)))
        elif kind == "attachment":
            motor = "att_left" if step["port"] == "E" else "att_right"
            lines.append(
                "{}att_run({}, {!r}, {!r})".format(
                    prefix, motor, step["speed_deg_s"], step["angle_deg"]
                )
            )
        elif kind == "wait":
            lines.append("{}wait({!r})".format(prefix, step["duration_ms"]))
        elif kind == "beep":
            lines.append(
                "{}beep({!r}, {!r})".format(
                    prefix, step["frequency_hz"], step["duration_ms"]
                )
            )
        elif kind == "turn_to":
            args = [repr(step["heading_deg"])]
            if "rate_deg_s" in step:
                args.append("rate={!r}".format(step["rate_deg_s"]))
            if step.get("through"):
                args.append("then=Stop.NONE")
            lines.append("{}turn_to({})".format(prefix, ", ".join(args)))
        elif kind == "wheel_turn":
            args = [
                repr(step["angle_deg"]),
                "locked={!r}".format(step["locked"].lower()),
            ]
            if "rate_deg_s" in step:
                args.append("rate={!r}".format(step["rate_deg_s"]))
            if step.get("through"):
                args.append("then=Stop.NONE")
            lines.append("{}wheel_turn({})".format(prefix, ", ".join(args)))
        elif kind == "wall_square":
            args = [repr(step["heading_deg"])]
            if "duty" in step:
                args.append("duty={!r}".format(step["duty"]))
            if "duration_ms" in step:
                args.append("duration={!r}".format(step["duration_ms"]))
            lines.append("{}wall_square({})".format(prefix, ", ".join(args)))
        elif kind == "set_speed":
            lines.append("{}set_speed({!r})".format(prefix, step["profile"]))
        elif kind == "set_heading":
            lines.append("{}set_heading({!r})".format(prefix, step["heading_deg"]))
        elif kind == "rush":
            lines.append("{}rush({!r})".format(prefix, step["enabled"]))
        elif kind == "stop":
            call = {
                "drive": "stop_drive",
                "all": "stop_all",
                "release": "release_drive",
            }[step["scope"]]
            lines.append("{}{}()".format(prefix, call))
        elif kind == "att_until_stalled":
            motor = "att_left" if step["port"] == "E" else "att_right"
            args = [motor, repr(step["speed_deg_s"])]
            if "duty_limit" in step:
                args.append("duty_limit={!r}".format(step["duty_limit"]))
            lines.append("{}att_run_until_stalled({})".format(prefix, ", ".join(args)))
        elif kind == "set_att_accel":
            lines.append("{}set_att_accel({!r})".format(prefix, step["accel_deg_s2"]))
        elif kind == "battery_check":
            lines.append("{}battery_check()".format(prefix))
        elif kind == "reset_start":
            lines.append("{}reset_start()".format(prefix))
        elif kind == "log":
            lines.append("{}log({!r})".format(prefix, step["message"]))
        elif kind == "if":
            lines.append("{}if {}:".format(prefix, _condition_expression(step["condition"])))
            _render_steps(lines, step["then"], indent + 1)
            if "else" in step:
                lines.append("{}else:".format(prefix))
                _render_steps(lines, step["else"], indent + 1)
        elif kind == "repeat":
            lines.append("{}for _ in range({}):".format(prefix, step["times"]))
            _render_steps(lines, step["steps"], indent + 1)
        elif kind == "parallel":
            drive_steps = []
            attachment_ports = []
            for branch in step["branches"]:
                resource = branch["resource"]
                if resource == "drive":
                    drive_steps = branch["steps"]
                    continue
                attachment = branch["steps"][0]
                motor = "att_left" if resource == "E" else "att_right"
                lines.append(
                    "{}att_run({}, {!r}, {!r}, wait=False)".format(
                        prefix,
                        motor,
                        attachment["speed_deg_s"],
                        attachment["angle_deg"],
                    )
                )
                attachment_ports.append((resource, motor))
            if drive_steps:
                _render_steps(lines, drive_steps, indent)
            for _, motor in attachment_ports:
                lines.append("{}att_wait({})".format(prefix, motor))


def _catalog_missions(source):
    tree = ast.parse(source)
    imported = set(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    registered = set()

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "MISSION_MODULES"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Tuple):
            raise ValueError("MISSION_MODULES must be a tuple")
        for entry in node.value.elts:
            if (
                isinstance(entry, ast.Tuple)
                and entry.elts
                and isinstance(entry.elts[0], ast.Constant)
                and isinstance(entry.elts[0].value, str)
            ):
                registered.add(entry.elts[0].value)
        break
    else:
        raise ValueError("MISSION_MODULES tuple was not found in mission_catalog.py")

    return imported, registered


def _render_catalog(source, module_names):
    imported, registered = _catalog_missions(source)
    additions = [name for name in module_names if name not in registered]
    if not additions:
        return source

    import_lines = []
    for name in additions:
        if name in imported:
            continue
        import_lines.extend(
            (
                "from {} import (".format(name),
                "    COLOR as _{}_color,".format(name),
                "    NAME as _{}_name,".format(name),
                "    run as _{}_run,".format(name),
                ")",
            )
        )

    if import_lines:
        marker = "MISSION_MODULES = ("
        position = source.find(marker)
        if position < 0:
            raise ValueError("MISSION_MODULES tuple was not found in mission_catalog.py")
        source = source[:position] + "\n".join(import_lines) + "\n\n" + source[position:]

    marker = "\n)\n\nTEST_MODULES = ("
    start = source.find("MISSION_MODULES = (")
    position = source.find(marker, start)
    if position < 0:
        raise ValueError("Could not locate the end of MISSION_MODULES")
    entries = "\n".join(
        "    ({!r}, _{}_name, _{}_run, _{}_color),".format(name, name, name, name)
        for name in additions
    )
    source = source[:position + 1] + entries + "\n" + source[position + 1:]
    return source


def build_archive():
    sources = [
        (ROOT / source_path, archive_path)
        for source_path, archive_path in ARCHIVE_FILES
    ]
    missing = [str(source) for source, _ in sources if not source.is_file()]
    if missing:
        raise FileNotFoundError(
            "Не найдены файлы проекта: {}".format(", ".join(missing))
        )

    missions = _load_json_missions()
    catalog_source = (ROOT / "mission_catalog.py").read_text(encoding="utf-8")
    catalog_source = _render_catalog(catalog_source, sorted(missions))
    generated = {
        module_name: _render_mission(module_name, mission)
        for module_name, mission in missions.items()
    }

    archive_files = {}
    for source, archive_name in sources:
        if archive_name == "mission_catalog.py":
            content = catalog_source.encode("utf-8")
        elif archive_name.endswith(".py") and archive_name[:-3] in generated:
            content = generated[archive_name[:-3]]
        else:
            content = source.read_bytes()
        archive_files[archive_name] = content

    for module_name, content in generated.items():
        archive_files[module_name + ".py"] = content

    MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with ZipFile(str(ARCHIVE_PATH), "w", ZIP_DEFLATED) as archive:
        for archive_name, content in archive_files.items():
            archive.writestr(archive_name, content)
    return ARCHIVE_PATH


def _extract_archive(archive_path, directory):
    """Распаковать собранный ZIP во временную папку и вернуть путь к main.py."""
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise FileNotFoundError("Архив не найден: {}".format(archive_path))

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with ZipFile(str(archive_path)) as archive:
        for name in archive.namelist():
            if not name.endswith(".py") or "/" in name or "\\" in name:
                raise ValueError(
                    "В архиве неожиданный файл: {!r}".format(name)
                )
        archive.extractall(str(directory))

    main_path = directory / "main.py"
    if not main_path.is_file():
        raise ValueError("В архиве нет main.py")
    return main_path


async def _wait_for_program_start(hub, status_flag, timeout=3.0):
    """Дождаться, пока хаб подтвердит, что пользовательская программа запущена."""
    started = asyncio.Event()

    def handle_status(status):
        if status & status_flag.USER_PROGRAM_RUNNING:
            started.set()

    subscription = hub.status_observable.subscribe(handle_status)
    try:
        try:
            await asyncio.wait_for(started.wait(), timeout)
        except asyncio.TimeoutError:
            return False
    finally:
        subscription.dispose()
    return True


async def _install_archive_async(archive_path, run_program, scan_timeout):
    from pybricksdev.ble import find_device
    from pybricksdev.ble.pybricks import StatusFlag
    from pybricksdev.connections.pybricks import PybricksHubBLE

    with TemporaryDirectory(prefix="op_install_") as directory:
        main_path = _extract_archive(archive_path, directory)

        print("Searching for a Pybricks hub over Bluetooth...")
        device = await find_device(timeout=scan_timeout)
        if device is None:
            raise RuntimeError(
                "Pybricks-хаб не найден. Проверь, что он включён и не подключён "
                "к Pybricks Code."
            )
        hub = PybricksHubBLE(device)
        await hub.connect()
        try:
            print("Connected to {}.".format(device.name or device.address))
            print("Uploading the archive to the hub...")
            await hub.download(str(main_path))
            print("Upload complete.")

            if not run_program:
                print(
                    "The program is in hub RAM and is not started. "
                    "Powering the hub off clears it."
                )
                return 0

            print("Starting the hub menu...")
            await hub.run(wait=False, print_output=True, line_handler=True)
            if not await _wait_for_program_start(hub, StatusFlag):
                print(
                    "The program was uploaded, but the hub did not confirm "
                    "that it started. Check the hub display."
                )
                return 1
            print("The hub menu is running. Disconnecting is safe.")
            return 0
        finally:
            await hub.disconnect()


def install_archive(archive_path, run_program=True, scan_timeout=20):
    """Загрузить собранный архив на хаб так же, как это делает Pybricks Code."""
    if sys.version_info < (3, 10):
        print(
            "Для Bluetooth-установки нужен Python 3.10+ и отдельное окружение: "
            "py -3 -m pip install -r requirements-mission-tester.txt"
        )
        return 1

    try:
        from bleak.exc import BleakError
        import pybricksdev  # noqa: F401
    except ImportError as error:
        print(
            "Bluetooth-зависимости не установлены: {}. Используй "
            ".venv-mission-tester\\Scripts\\python.exe или установи "
            "requirements-mission-tester.txt.".format(error)
        )
        return 1

    try:
        return asyncio.run(
            _install_archive_async(Path(archive_path), run_program, scan_timeout)
        )
    except asyncio.TimeoutError:
        print("Bluetooth-поиск хаба истёк. Проверь, что хаб включён.")
        return 1
    except (
        BleakError,
        OSError,
        RuntimeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:
        print("Не удалось установить архив: {}".format(error))
        return 1


USAGE = "Usage: build_archive.py [--install [--no-run]]"


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    install = False
    run_program = True

    for argument in arguments:
        if argument == "--install":
            install = True
        elif argument == "--no-run":
            run_program = False
        elif argument in ("-h", "--help"):
            print(USAGE)
            return 0
        else:
            print(USAGE)
            return 2

    if not install and not run_program:
        print("--no-run используется только вместе с --install.")
        return 2

    archive_path = build_archive()
    print("Created archive: {}".format(archive_path))
    if not install:
        return 0
    return install_archive(archive_path, run_program=run_program)


if __name__ == "__main__":
    sys.exit(main())
