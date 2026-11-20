from mission_1 import (
    COLOR as _mission_1_color,
    NAME as _mission_1_name,
    run as _mission_1_run,
)
from mission_2 import (
    COLOR as _mission_2_color,
    NAME as _mission_2_name,
    run as _mission_2_run,
)
from system_check import (
    COLOR as _system_check_color,
    NAME as _system_check_name,
    run as _system_check_run,
)

MISSION_MODULES = (
    ('mission_1', _mission_1_name, _mission_1_run, _mission_1_color),
    ('mission_2', _mission_2_name, _mission_2_run, _mission_2_color),
)

TEST_MODULES = (
    ('system_check', _system_check_name, _system_check_run, _system_check_color),
)
