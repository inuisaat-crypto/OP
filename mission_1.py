from core import arc, stop_drive, straight, turn

NAME = 'Маршрут OP'
COLOR = 'MAGENTA'

def run_op_route():
    # Put the robot at the selected start position and heading.
    # Each grid cell represents 25 mm.
    straight(275, speed=100)
    turn(90, rate=90)
    straight(50, speed=100)
    turn(90, rate=90)
    straight(50, speed=100)
    turn(90, rate=90)
    straight(50, speed=100)
    turn(90, rate=90)
    straight(25, speed=100)
    turn(-180, rate=90)
    straight(225, speed=100)

def run():
    run_op_route()
