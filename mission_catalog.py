from system_check import (
    COLOR as _system_check_color,
    NAME as _system_check_name,
    run as _system_check_run,
)

# JSON-миссии из missions/*.json build_archive.py подставляет в этот каталог
# при сборке архива, поэтому в исходнике их нет.
MISSION_MODULES = (
)

TEST_MODULES = (
    ('system_check', _system_check_name, _system_check_run, _system_check_color),
)
