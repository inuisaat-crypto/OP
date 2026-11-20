"""Record a hand-guided path using the drive encoders and hub gyro."""

from core import left_motor, right_motor, robot, hub
from pybricks.parameters import Button, Color
from pybricks.tools import StopWatch, wait


SAMPLE_INTERVAL_MS = 100
MAX_RECORDING_SAMPLES = 1200


def _wait_for_release():
    while hub.buttons.pressed():
        wait(10)


def _stop_and_release_drive():
    robot.stop()
    left_motor.stop()
    right_motor.stop()


def record_hand_guided_mission():
    hub.system.set_stop_button(None)
    hub.display.char("S")
    hub.light.on(Color.CYAN)
    print("OPREC_READY")
    while True:
        pressed = hub.buttons.pressed()
        if Button.CENTER in pressed:
            _wait_for_release()
            break
        if Button.LEFT in pressed:
            _wait_for_release()
            print("OPREC_CANCELLED")
            return False
        wait(10)

    _stop_and_release_drive()
    wait(100)
    robot.reset(0, 0)
    samples = [(round(robot.distance()), round(hub.imu.heading() * 10))]
    timer = StopWatch()
    last_sample = 0
    hub.display.char("1")
    hub.light.on(Color.ORANGE)
    hub.speaker.beep(700, 80)

    while True:
        pressed = hub.buttons.pressed()
        if Button.CENTER in pressed:
            _wait_for_release()
            break
        if Button.LEFT in pressed:
            _wait_for_release()
            _stop_and_release_drive()
            print("OPREC_CANCELLED")
            return False

        elapsed = timer.time()
        if elapsed - last_sample >= SAMPLE_INTERVAL_MS:
            samples.append(
                (round(robot.distance()), round(hub.imu.heading() * 10))
            )
            last_sample = elapsed
            if len(samples) >= MAX_RECORDING_SAMPLES:
                _stop_and_release_drive()
                hub.display.char("!")
                hub.light.on(Color.RED)
                print("OPREC_ERROR,LIMIT")
                return False
        wait(10)

    _stop_and_release_drive()
    final_sample = (round(robot.distance()), round(hub.imu.heading() * 10))
    if final_sample != samples[-1]:
        samples.append(final_sample)
    if len(samples) >= MAX_RECORDING_SAMPLES:
        hub.display.char("!")
        hub.light.on(Color.RED)
        print("OPREC_ERROR,LIMIT")
        return False
    initial_distance, initial_heading = samples[0]
    moved = any(
        abs(distance - initial_distance) >= 1
        or abs(heading - initial_heading) >= 10
        for distance, heading in samples[1:]
    )
    if not moved:
        hub.display.char("!")
        hub.light.on(Color.RED)
        print("OPREC_ERROR,NO_MOVEMENT")
        return False

    hub.display.char("D")
    hub.light.on(Color.GREEN)
    print("OPREC_BEGIN,{}".format(len(samples)))
    for distance, heading_tenths in samples:
        print("OPREC_SAMPLE,{},{}".format(distance, heading_tenths))
    print("OPREC_DONE")
    hub.speaker.beep(900, 100)
    return True
