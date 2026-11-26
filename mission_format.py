"""Versioned JSON mission validation for desktop tools."""

import json
import math


class MissionFormatError(ValueError):
    pass


COLORS = frozenset(
    (
        "BLACK",
        "BLUE",
        "CYAN",
        "GREEN",
        "MAGENTA",
        "ORANGE",
        "RED",
        "VIOLET",
        "WHITE",
        "YELLOW",
    )
)
STEP_TYPES = frozenset(
    (
        "straight",
        "turn",
        "turn_to",
        "wheel_turn",
        "arc",
        "wall_square",
        "attachment",
        "att_until_stalled",
        "set_att_accel",
        "wait",
        "beep",
        "log",
        "battery_check",
        "set_speed",
        "set_heading",
        "rush",
        "reset_start",
        "stop",
        "if",
        "repeat",
        "parallel",
    )
)
MAX_STEPS = 200
MAX_REPEAT = 100
MAX_NESTING = 12
# Движения, у которых есть then=Stop.NONE: только они могут быть «на проход».
MOVEMENT_TYPES = frozenset(("straight", "turn", "turn_to", "wheel_turn", "arc"))


def _check_keys(value, required, allowed, location):
    missing = required.difference(value)
    extra = set(value).difference(allowed)
    if missing:
        raise MissionFormatError(
            "{} is missing fields: {}".format(location, ", ".join(sorted(missing)))
        )
    if extra:
        raise MissionFormatError(
            "{} has unknown fields: {}".format(location, ", ".join(sorted(extra)))
        )


def _number(value, key, location, minimum, maximum, nonzero=False, integer=False):
    number = value.get(key)
    valid_type = type(number) is int if integer else type(number) in (int, float)
    if not valid_type or not math.isfinite(number):
        expected = "an integer" if integer else "a finite number"
        raise MissionFormatError(
            "{}.{} must be {}".format(location, key, expected)
        )
    if number < minimum or number > maximum or (nonzero and number == 0):
        raise MissionFormatError(
            "{}.{} must be {}{} and between {} and {}".format(
                location,
                key,
                "nonzero " if nonzero else "",
                "integer" if integer else "number",
                minimum,
                maximum,
            )
        )
    return number


def _validate_condition(condition, location):
    if not isinstance(condition, dict):
        raise MissionFormatError("{} condition must be an object".format(location))
    required = {"sensor", "operator", "value"}
    allowed = required | {"port"}
    _check_keys(condition, required, allowed, location)
    if condition["sensor"] not in (
        "heading_deg",
        "battery_mv",
        "attachment_angle_deg",
    ):
        raise MissionFormatError(
            "{} condition has unsupported sensor {!r}".format(
                location, condition["sensor"]
            )
        )
    if condition["sensor"] == "attachment_angle_deg":
        if condition.get("port") not in ("E", "F"):
            raise MissionFormatError("{} condition port must be E or F".format(location))
    elif "port" in condition:
        raise MissionFormatError(
            "{} condition port is only valid for an attachment sensor".format(location)
        )
    if condition["operator"] not in ("<", "<=", "==", "!=", ">=", ">"):
        raise MissionFormatError("{} condition operator is invalid".format(location))
    _number(condition, "value", location, -1000000, 1000000)


def _validate_sequence(steps, location, depth=0):
    if depth > MAX_NESTING:
        raise MissionFormatError(
            "{} exceeds maximum nesting depth of {}".format(location, MAX_NESTING)
        )
    if not isinstance(steps, list) or not steps:
        raise MissionFormatError("{} must be a non-empty list".format(location))
    if len(steps) > MAX_STEPS:
        raise MissionFormatError(
            "{} cannot contain more than {} steps".format(location, MAX_STEPS)
        )
    for index, step in enumerate(steps):
        _validate_step(step, "{} step {}".format(location, index + 1), depth)
        if step.get("through"):
            following = steps[index + 1] if index + 1 < len(steps) else None
            if following is None or following.get("type") not in MOVEMENT_TYPES:
                raise MissionFormatError(
                    "{} step {} is 'through' but the next command is not a movement".format(
                        location, index + 1
                    )
                )


def _validate_step(step, location, depth):
    if not isinstance(step, dict):
        raise MissionFormatError("{} must be an object".format(location))

    kind = step.get("type")
    if kind not in STEP_TYPES:
        raise MissionFormatError(
            "{} has unsupported type {!r}".format(location, kind)
        )
    if "through" in step:
        if kind not in MOVEMENT_TYPES:
            raise MissionFormatError(
                "{}: 'through' is only valid for movements".format(location)
            )
        if type(step["through"]) is not bool:
            raise MissionFormatError(
                "{}.through must be true or false".format(location)
            )

    if kind == "straight":
        required = {"type", "distance_mm"}
        allowed = required | {"speed_mm_s", "through"}
        _check_keys(step, required, allowed, location)
        _number(step, "distance_mm", location, -5000, 5000, nonzero=True)
        if "speed_mm_s" in step:
            _number(step, "speed_mm_s", location, 1, 800)
    elif kind == "turn":
        required = {"type", "angle_deg"}
        allowed = required | {"rate_deg_s", "through"}
        _check_keys(step, required, allowed, location)
        _number(step, "angle_deg", location, -360, 360, nonzero=True)
        if "rate_deg_s" in step:
            _number(step, "rate_deg_s", location, 1, 360)
    elif kind == "arc":
        required = {"type", "radius_mm", "angle_deg"}
        allowed = required | {"speed_mm_s", "through"}
        _check_keys(step, required, allowed, location)
        _number(step, "radius_mm", location, -5000, 5000, nonzero=True)
        _number(step, "angle_deg", location, -360, 360, nonzero=True)
        if "speed_mm_s" in step:
            _number(step, "speed_mm_s", location, 1, 800)
    elif kind == "attachment":
        required = {"type", "port", "angle_deg", "speed_deg_s"}
        _check_keys(step, required, required, location)
        if step["port"] not in ("E", "F"):
            raise MissionFormatError(
                "{}.port must be E or F".format(location)
            )
        _number(step, "angle_deg", location, -360, 360, nonzero=True)
        _number(step, "speed_deg_s", location, 1, 800)
    elif kind == "wait":
        required = {"type", "duration_ms"}
        _check_keys(step, required, required, location)
        _number(step, "duration_ms", location, 0, 30000, integer=True)
    elif kind == "beep":
        required = {"type", "frequency_hz", "duration_ms"}
        _check_keys(step, required, required, location)
        _number(step, "frequency_hz", location, 50, 4000, integer=True)
        _number(step, "duration_ms", location, 1, 1000, integer=True)
    elif kind == "turn_to":
        required = {"type", "heading_deg"}
        allowed = required | {"rate_deg_s", "through"}
        _check_keys(step, required, allowed, location)
        _number(step, "heading_deg", location, -360, 360)
        if "rate_deg_s" in step:
            _number(step, "rate_deg_s", location, 1, 360)
    elif kind == "wheel_turn":
        required = {"type", "angle_deg", "locked"}
        allowed = required | {"rate_deg_s", "through"}
        _check_keys(step, required, allowed, location)
        if step["locked"] not in ("LEFT", "RIGHT"):
            raise MissionFormatError(
                "{}.locked must be LEFT or RIGHT".format(location)
            )
        _number(step, "angle_deg", location, -360, 360, nonzero=True)
        if "rate_deg_s" in step:
            _number(step, "rate_deg_s", location, 1, 360)
    elif kind == "wall_square":
        required = {"type", "heading_deg"}
        allowed = required | {"duty", "duration_ms"}
        _check_keys(step, required, allowed, location)
        _number(step, "heading_deg", location, -360, 360)
        if "duty" in step:
            _number(step, "duty", location, -100, 100, nonzero=True)
        if "duration_ms" in step:
            _number(step, "duration_ms", location, 50, 3000, integer=True)
    elif kind == "set_speed":
        required = {"type", "profile"}
        _check_keys(step, required, required, location)
        if step["profile"] not in ("FAST", "MEDIUM", "SLOW", "SLOWW"):
            raise MissionFormatError(
                "{}.profile must be FAST, MEDIUM, SLOW, or SLOWW".format(location)
            )
    elif kind == "set_heading":
        required = {"type", "heading_deg"}
        _check_keys(step, required, required, location)
        _number(step, "heading_deg", location, -360, 360)
    elif kind == "rush":
        required = {"type", "enabled"}
        _check_keys(step, required, required, location)
        if type(step["enabled"]) is not bool:
            raise MissionFormatError("{}.enabled must be true or false".format(location))
    elif kind == "stop":
        required = {"type", "scope"}
        _check_keys(step, required, required, location)
        if step["scope"] not in ("drive", "all", "release"):
            raise MissionFormatError(
                "{}.scope must be drive, all, or release".format(location)
            )
    elif kind == "att_until_stalled":
        required = {"type", "port", "speed_deg_s"}
        allowed = required | {"duty_limit"}
        _check_keys(step, required, allowed, location)
        if step["port"] not in ("E", "F"):
            raise MissionFormatError("{}.port must be E or F".format(location))
        _number(step, "speed_deg_s", location, -1000, 1000, nonzero=True)
        if "duty_limit" in step:
            _number(step, "duty_limit", location, 1, 100, integer=True)
    elif kind == "set_att_accel":
        required = {"type", "accel_deg_s2"}
        _check_keys(step, required, required, location)
        _number(step, "accel_deg_s2", location, 10, 2000)
    elif kind == "battery_check":
        _check_keys(step, {"type"}, {"type"}, location)
    elif kind == "reset_start":
        _check_keys(step, {"type"}, {"type"}, location)
    elif kind == "log":
        required = {"type", "message"}
        _check_keys(step, required, required, location)
        message = step["message"]
        if not isinstance(message, str) or not message.strip() or len(message) > 120:
            raise MissionFormatError(
                "{}.message must be 1 to 120 characters".format(location)
            )
    elif kind == "if":
        required = {"type", "condition", "then"}
        allowed = required | {"else"}
        _check_keys(step, required, allowed, location)
        _validate_condition(step["condition"], location)
        _validate_sequence(step["then"], location + ".then", depth + 1)
        if "else" in step:
            _validate_sequence(step["else"], location + ".else", depth + 1)
    elif kind == "repeat":
        required = {"type", "times", "steps"}
        _check_keys(step, required, required, location)
        _number(step, "times", location, 1, MAX_REPEAT, integer=True)
        _validate_sequence(step["steps"], location + ".steps", depth + 1)
    elif kind == "parallel":
        required = {"type", "branches"}
        _check_keys(step, required, required, location)
        branches = step["branches"]
        if not isinstance(branches, list) or len(branches) < 2:
            raise MissionFormatError(
                "{}.branches must contain at least two resource lanes".format(location)
            )
        resources = set()
        for index, branch in enumerate(branches):
            branch_location = "{}.branches[{}]".format(location, index)
            if not isinstance(branch, dict):
                raise MissionFormatError("{} must be an object".format(branch_location))
            _check_keys(
                branch,
                {"resource", "steps"},
                {"resource", "steps"},
                branch_location,
            )
            resource = branch["resource"]
            if resource not in ("drive", "E", "F"):
                raise MissionFormatError(
                    "{}.resource must be drive, E, or F".format(branch_location)
                )
            if resource in resources:
                raise MissionFormatError(
                    "{} duplicates resource {!r}".format(location, resource)
                )
            resources.add(resource)
            _validate_sequence(branch["steps"], branch_location + ".steps", depth + 1)
            if resource == "drive":
                for branch_step in branch["steps"]:
                    if branch_step.get("type") not in (
                        "straight",
                        "turn",
                        "turn_to",
                        "wheel_turn",
                        "arc",
                        "wall_square",
                        "wait",
                    ):
                        raise MissionFormatError(
                            "{} drive lane only supports movement and wait blocks".format(
                                branch_location
                            )
                        )
            else:
                if (
                    len(branch["steps"]) != 1
                    or branch["steps"][0].get("type") != "attachment"
                    or branch["steps"][0].get("port") != resource
                ):
                    raise MissionFormatError(
                        "{} must contain exactly one attachment command for port {}".format(
                            branch_location, resource
                        )
                    )


def validate_mission(mission):
    if not isinstance(mission, dict):
        raise MissionFormatError("Mission must be a JSON object")

    required = {"version", "name", "color", "steps"}
    _check_keys(mission, required, required | {"start_pose"}, "Mission")

    if type(mission["version"]) is not int or mission["version"] != 1:
        raise MissionFormatError("Mission version must be 1")
    if not isinstance(mission["name"], str) or not mission["name"].strip():
        raise MissionFormatError("Mission name must not be empty")
    if not isinstance(mission["color"], str) or mission["color"] not in COLORS:
        raise MissionFormatError(
            "Unsupported color {!r}".format(mission["color"])
        )

    if "start_pose" in mission:
        pose = mission["start_pose"]
        if not isinstance(pose, dict):
            raise MissionFormatError("Mission.start_pose must be an object")
        pose_fields = {"x_mm", "y_mm", "heading_deg"}
        _check_keys(pose, pose_fields, pose_fields, "Mission.start_pose")
        _number(pose, "x_mm", "Mission.start_pose", 0, 2000)
        _number(pose, "y_mm", "Mission.start_pose", 0, 1140)
        _number(pose, "heading_deg", "Mission.start_pose", -360, 360)

    _validate_sequence(mission["steps"], "Mission.steps")
    return mission


def load_mission(path):
    try:
        with open(str(path), "r", encoding="utf-8") as source:
            mission = json.load(source)
    except json.JSONDecodeError as error:
        raise MissionFormatError(
            "Invalid JSON at line {}, column {}: {}".format(
                error.lineno, error.colno, error.msg
            )
        ) from error
    return validate_mission(mission)
