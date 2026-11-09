"""Проверка маршрута и генерация программ для Pybricks."""

from collections.abc import Mapping, Sequence


HEADINGS = ("N", "E", "S", "W")
HEADING_DELTAS = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}
HEADING_INDEX = {heading: index for index, heading in enumerate(HEADINGS)}
LEFT_MOTOR_PORT = "E"
RIGHT_MOTOR_PORT = "A"
WHEEL_DIAMETER_MM = 60
AXLE_TRACK_MM = 148
CELL_DISTANCE_MM = 25

Point = tuple[int, int]
Route = Sequence[Point]


def _validate_route(route: Route) -> tuple[Point, ...]:
    """Проверяет, что маршрут состоит из соседних клеток с целыми координатами."""
    points = tuple(route)
    if not points:
        raise ValueError("Маршрут не может быть пустым.")
    if any(
        not isinstance(point, (tuple, list))
        or len(point) != 2
        or any(type(coordinate) is not int for coordinate in point)
        for point in points
    ):
        raise ValueError("Координаты маршрута должны быть целыми числами.")
    if any(
        abs(x1 - x2) + abs(y1 - y2) != 1
        for (x1, y1), (x2, y2) in zip(points, points[1:])
    ):
        raise ValueError("Каждый шаг маршрута должен вести в соседнюю клетку.")
    return points


def validate_route_data(
    data: object,
) -> tuple[int, int, Point, str, list[Point]]:
    """Проверяет JSON-маршрут до изменения состояния редактора."""
    if not isinstance(data, Mapping) or type(data.get("version")) is not int:
        raise ValueError("Файл содержит некорректный формат маршрута.")
    if data["version"] not in (1, 2):
        raise ValueError("Поддерживаются версии маршрута 1 и 2.")

    grid = data.get("grid")
    start_data = data.get("start")
    route_data = data.get("route")
    if not isinstance(grid, Mapping) or not isinstance(start_data, Mapping):
        raise ValueError("В файле отсутствуют параметры сетки или старта.")
    if not isinstance(route_data, list):
        raise ValueError("Список точек маршрута имеет неверный формат.")

    values = (
        grid.get("columns"),
        grid.get("rows"),
        start_data.get("x"),
        start_data.get("y"),
    )
    if any(type(value) is not int for value in values):
        raise ValueError("Размеры сетки и координаты старта должны быть целыми.")
    columns, rows, start_x, start_y = values
    if not 2 <= columns <= 100 or not 2 <= rows <= 100:
        raise ValueError("Размеры сетки должны быть от 2 до 100 клеток.")

    heading = start_data.get("heading")
    if not isinstance(heading, str) or heading not in HEADINGS:
        raise ValueError("Направление старта указано неверно.")

    start = (start_x, start_y)
    route = []
    for point in route_data:
        if not isinstance(point, Mapping):
            raise ValueError("Точка маршрута имеет неверный формат.")
        x, y = point.get("x"), point.get("y")
        if type(x) is not int or type(y) is not int:
            raise ValueError("Координаты маршрута должны быть целыми числами.")
        route.append((x, y))

    points = _validate_route(route)
    if points[0] != start:
        raise ValueError("Маршрут должен начинаться в стартовой клетке.")
    if any(not (0 <= x < columns and 0 <= y < rows) for x, y in points):
        raise ValueError("Точка маршрута находится за пределами сетки.")
    cell_mm = grid.get("cell_mm", CELL_DISTANCE_MM)
    if type(cell_mm) is not int or not 5 <= cell_mm <= 500:
        raise ValueError("Шаг клетки должен быть целым числом от 5 до 500 мм.")
    segments = data.get("segments", [])
    if not isinstance(segments, list) or len(segments) not in (0, len(points) - 1):
        raise ValueError("Для каждого участка должна быть задана одна настройка движения.")
    for segment in segments:
        if not isinstance(segment, Mapping) or segment.get("mode", "forward") not in ("forward", "backward", "arc"):
            raise ValueError("В маршруте найден неизвестный тип движения.")
        speed = segment.get("speed")
        if speed is not None and (type(speed) is not int or not 10 <= speed <= 1000):
            raise ValueError("Скорость участка должна быть от 10 до 1000 мм/с.")
    markers = data.get("markers", {})
    if not isinstance(markers, Mapping):
        raise ValueError("Метки маршрута имеют неверный формат.")
    for index, entries in markers.items():
        if not str(index).isdigit() or int(index) >= len(points) or not isinstance(entries, list):
            raise ValueError("Метка ссылается на несуществующую точку маршрута.")
        for marker in entries:
            if not isinstance(marker, Mapping) or marker.get("action") not in ("turn", "stop", "label"):
                raise ValueError("Неизвестное действие в метке маршрута.")
            if marker.get("action") == "turn" and (type(marker.get("angle", 90)) is not int or not -360 <= marker.get("angle", 90) <= 360):
                raise ValueError("Угол поворота в метке должен быть от -360 до 360 градусов.")
            if marker.get("action") == "label" and not isinstance(marker.get("text", ""), str):
                raise ValueError("Текст метки должен быть строкой.")
    return columns, rows, start, heading, list(points)


def _pybricks_setup_lines(
    settings: tuple[int, int, int, int], reverse_motor_directions: bool = False
) -> list[str]:
    straight_speed, straight_acceleration, turn_rate, turn_acceleration = settings
    left_motor = (
        "left_motor = Motor(Port.{}, Direction.COUNTERCLOCKWISE)".format(
            LEFT_MOTOR_PORT
        )
        if reverse_motor_directions
        else "left_motor = Motor(Port.{})".format(LEFT_MOTOR_PORT)
    )
    right_motor = (
        "right_motor = Motor(Port.{})".format(RIGHT_MOTOR_PORT)
        if reverse_motor_directions
        else "right_motor = Motor(Port.{}, Direction.COUNTERCLOCKWISE)".format(
            RIGHT_MOTOR_PORT
        )
    )
    return [
        "from pybricks.hubs import PrimeHub",
        "from pybricks.pupdevices import Motor",
        "from pybricks.parameters import Direction, Port",
        "from pybricks.robotics import DriveBase",
        "",
        "hub = PrimeHub()",
        left_motor,
        right_motor,
        "drive_base = DriveBase(",
        "    left_motor,",
        "    right_motor,",
        "    wheel_diameter={}, ".format(WHEEL_DIAMETER_MM),
        "    axle_track={}, ".format(AXLE_TRACK_MM),
        ")",
        "drive_base.settings({}, {}, {}, {})".format(
            straight_speed, straight_acceleration, turn_rate, turn_acceleration
        ),
        "",
    ]


def _wrap_drive_commands(
    commands: Sequence[str],
    settings: tuple[int, int, int, int],
    reverse_motor_directions: bool = False,
) -> str:
    lines = _pybricks_setup_lines(settings, reverse_motor_directions)
    lines.append("try:")
    lines.extend("    {}".format(command) for command in commands)
    lines.extend(("finally:", "    drive_base.stop()", ""))
    return "\n".join(lines)


def route_end_heading_index(route: Route, initial_heading: str) -> int:
    """Возвращает направление робота после прохождения заданного маршрута."""
    points = _validate_route(route)
    if initial_heading not in HEADING_INDEX:
        raise ValueError("Направление старта указано неверно.")
    heading_index = HEADING_INDEX[initial_heading]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        delta = (x2 - x1, y2 - y1)
        target_heading = next(
            index
            for index, heading in enumerate(HEADINGS)
            if HEADING_DELTAS[heading] == delta
        )
        if target_heading != (heading_index + 2) % len(HEADINGS):
            heading_index = target_heading
    return heading_index


def generate_pybricks_program(
    route: Route,
    initial_heading: str,
    reverse_motor_directions: bool = False,
    *,
    cell_distance_mm: int = CELL_DISTANCE_MM,
    segments: Sequence[Mapping] | None = None,
    markers: Mapping[int, Sequence[Mapping]] | None = None,
) -> str:
    """Преобразует клетки маршрута в безопасно обёрнутые команды DriveBase."""
    points = _validate_route(route)
    if initial_heading not in HEADING_INDEX:
        raise ValueError("Направление старта указано неверно.")

    if type(cell_distance_mm) is not int or not 1 <= cell_distance_mm <= 1000:
        raise ValueError("Шаг сетки должен быть целым числом от 1 до 1000 мм.")
    segments = list(segments or ())
    markers = markers or {}
    commands = [
        "# Put the robot at the selected start position and heading.",
        "# Each grid cell represents {} mm.".format(cell_distance_mm),
    ]
    heading_index = HEADING_INDEX[initial_heading]
    for edge_index, ((x1, y1), (x2, y2)) in enumerate(zip(points, points[1:])):
        delta = (x2 - x1, y2 - y1)
        direction = next(h for h, step in HEADING_DELTAS.items() if step == delta)
        target_index = HEADING_INDEX[direction]
        distance = cell_distance_mm
        segment = segments[edge_index] if edge_index < len(segments) else {}
        mode = segment.get("mode", "forward")
        if mode not in ("forward", "backward", "arc"):
            raise ValueError("Неизвестный режим участка.")
        effective_heading = (target_index + (2 if mode == "backward" else 0)) % 4
        turn_steps = (effective_heading - heading_index + 2) % 4 - 2
        if turn_steps:
            commands.append("drive_base.turn({})".format(turn_steps * 90))
        speed = segment.get("speed")
        if speed is not None and (type(speed) is not int or not 10 <= speed <= 1000):
            raise ValueError("Скорость участка должна быть от 10 до 1000 мм/с.")
        commands.append("drive_base.settings({}, 200, 90, 180)".format(speed or 100))
        if mode == "arc":
            curve = segment.get("curve", 45)
            if type(curve) is not int or not 1 <= abs(curve) <= 360:
                raise ValueError("Угол дуги должен быть от 1 до 360 градусов.")
            commands.append("drive_base.curve(50, {})".format(curve))
        else:
            sign = -1 if mode == "backward" else 1
            commands.append("drive_base.straight({})".format(sign * distance))
        heading_index = effective_heading
        for marker in markers.get(edge_index + 1, ()):
            action = marker.get("action")
            if action == "turn":
                angle = marker.get("angle", 90)
                if type(angle) is not int or not -360 <= angle <= 360:
                    raise ValueError("Поворот на месте: угол от -360 до 360.")
                commands.append("drive_base.turn({})".format(angle))
                heading_index = (heading_index + round(angle / 90)) % 4
            elif action == "stop":
                commands.append("drive_base.stop()")
            elif action == "label":
                label = marker.get("text", "")
                if not isinstance(label, str):
                    raise ValueError("Текст метки должен быть строкой.")
                commands.append("# Маркер: " + label.replace("\n", " ")[:100])

    if len(points) == 1:
        commands.append('print("No movement: route contains only the start point.")')
    return _wrap_drive_commands(
        commands, (100, 200, 90, 180), reverse_motor_directions
    )


def generate_pybricks_test_program(
    reverse_motor_directions: bool = False,
) -> str:
    """Генерирует короткую проверку движения с возвратом в исходную точку."""
    commands = [
        "# Straight-drive check: forward, then reverse along the same line.",
        "drive_base.straight(50)",
        "drive_base.straight(-50)",
    ]
    return _wrap_drive_commands(
        commands, (50, 100, 45, 90), reverse_motor_directions
    )
