"""Точка входа проекта OP для Pybricks Code."""

from core import left_motor, right_motor, rush, stop_all
from mission_catalog import MISSION_MODULES, TEST_MODULES
from menu import run_mission_menu


def main():
    try:
        run_mission_menu(MISSION_MODULES, TEST_MODULES)
    finally:
        # Любой выход (кнопка-стоп, ошибка при DEBUG_RAISE) оставляет хаб в покое:
        # быстрый режим выключен, моторы стоят, следующий запуск начнётся с точного.
        try:
            rush(False)
        finally:
            try:
                stop_all()
            finally:
                left_motor.stop()
                right_motor.stop()


if __name__ == "__main__":
    main()
