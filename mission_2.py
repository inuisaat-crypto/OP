from core import arc, stop_drive, straight, turn

NAME = 'route'
COLOR = 'MAGENTA'

def run_op_route():
    # Put the robot at the selected start position and heading.
    # Each grid cell represents 25 mm.
    straight(825, speed=750)

def run():
    run_op_route()
