from core import MoveError, att_left, att_right, att_run, hub, straight, turn
from pybricks.parameters import Stop


NAME = "Квадрат и навески"
COLOR = "YELLOW"

SQUARE_SIDE_MM = 200
SQUARE_SPEED = 100
TURN_RATE = 60
ATTACHMENT_SPEED = 90
ATTACHMENT_SWEEP_DEGREES = 45


def _require_success(success, action):
    if not success:
        raise MoveError("Не удалось выполнить: {}".format(action))


def _test_attachment(motor, name):
    _require_success(
        att_run(
            motor,
            ATTACHMENT_SPEED,
            ATTACHMENT_SWEEP_DEGREES,
            then=Stop.COAST,
        ),
        name,
    )
    _require_success(
        att_run(
            motor,
            ATTACHMENT_SPEED,
            -ATTACHMENT_SWEEP_DEGREES,
            then=Stop.COAST,
        ),
        name,
    )


def run():
    for side in range(4):
        _require_success(
            straight(SQUARE_SIDE_MM, speed=SQUARE_SPEED),
            "сторона квадрата {}".format(side + 1),
        )
        _require_success(
            turn(90, rate=TURN_RATE),
            "поворот квадрата {}".format(side + 1),
        )

    _test_attachment(att_left, "навеска E")
    _test_attachment(att_right, "навеска F")
    hub.speaker.beep(880, 150)
