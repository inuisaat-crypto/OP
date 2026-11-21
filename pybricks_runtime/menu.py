"""Меню хаба: статический каталог миссий и тестов.

Меню не должно падать на соревнованиях: любая ошибка внутри миссии (кроме
SystemExit от кнопки-стопа) останавливает моторы и возвращает управление
в список. При DEBUG_RAISE = True исключение пробрасывается с traceback —
это режим тренировки, когда ошибку нужно увидеть целиком.
"""

import sys


def next_mission_index(current, direction, mission_count):
    if type(mission_count) is not int or mission_count <= 0:
        raise ValueError("Для меню нужна хотя бы одна миссия.")
    if type(current) is not int or type(direction) is not int:
        raise ValueError("Индекс и направление должны быть целыми числами.")
    return (current + direction) % mission_count


def _category_from_button(pressed, Button):
    if Button.LEFT in pressed:
        return 0
    if Button.RIGHT in pressed:
        return 1
    return None


def _items_from_catalog(entries, Color):
    items = []
    for module_name, name, run, color_name in entries:
        if not callable(run):
            raise ValueError("{} должен объявлять функцию run().".format(module_name))
        if not isinstance(name, str) or not name:
            raise ValueError(
                "{}: NAME должен быть непустой строкой.".format(module_name)
            )
        if not isinstance(color_name, str):
            raise ValueError(
                "{}: COLOR должен быть именем цвета.".format(module_name)
            )
        color = getattr(Color, color_name, None)
        if color is None:
            raise ValueError(
                "{}: неизвестный цвет {!r}.".format(module_name, color_name)
            )
        items.append((name, run, color))
    return items


def discover_missions(entries, Color):
    return _items_from_catalog(entries, Color)


def discover_tests(entries, Color):
    return _items_from_catalog(entries, Color)


def _wait_for_release(hub, wait):
    while hub.buttons.pressed():
        wait(10)


def _show_categories(hub, selected, Color):
    hub.display.off()
    tiles = (
        ((0, 1), (0, 2), (1, 1), (1, 2)),
        ((3, 1), (3, 2), (4, 1), (4, 2)),
    )
    for category, pixels in enumerate(tiles):
        brightness = 100 if category == selected else 40
        for row, column in pixels:
            hub.display.pixel(row, column, brightness)
    colors = (Color.CYAN, Color.YELLOW)
    labels = ("Миссии", "Тесты")
    hub.light.on(colors[selected])
    print("OP | Раздел: {}".format(labels[selected]))


def _execute_mission(mission, reset_start, battery_check, MoveError, DEBUG_RAISE):
    """Выполнить миссию и вернуть 'ok' / 'stopped' / 'failed'.

    Моторы здесь НЕ останавливаются: это делает вызывающий в finally, чтобы
    остановка случилась и тогда, когда при DEBUG_RAISE исключение уходит наверх.
    """
    try:
        reset_start()
        battery_check()
        mission()
        return "ok"
    except SystemExit:
        return "stopped"
    except KeyboardInterrupt:
        return "stopped"
    except MoveError as error:
        print("OP | Ошибка движения: {}".format(error))
        return "failed"
    except Exception as error:
        if DEBUG_RAISE:
            raise
        print("OP | Сбой миссии: {}: {}".format(type(error).__name__, error))
        if hasattr(sys, "print_exception"):
            try:
                sys.print_exception(error)
            except Exception:
                pass
        return "failed"


def _cleanup(hub, Button, rush, stop_all, left_motor, right_motor):
    """Чистое состояние хаба: обычный режим, моторы стоят, кнопка-стоп свободна."""
    rush(False)
    stop_all()
    left_motor.stop()
    right_motor.stop()
    hub.system.set_stop_button(None)


def _run_section(
    hub,
    title,
    items,
    Button,
    Color,
    wait,
    reset_start,
    battery_check,
    left_motor,
    right_motor,
    stop_all,
    rush,
    MoveError,
    DEBUG_RAISE,
):
    if not items:
        print("OP | В разделе «{}» нет файлов.".format(title))
        hub.display.number(0)
        hub.light.on(Color.RED)
        wait(800)
        return

    entries = list(items) + [("Назад", None, Color.WHITE)]
    selected = 0
    while True:
        label, mission, color = entries[selected]
        if mission is None:
            hub.display.char("<")
        else:
            hub.display.number(selected + 1)
        hub.light.on(color)
        print("OP | {}: {}".format(title, label))

        while True:
            pressed = hub.buttons.pressed()
            if Button.LEFT in pressed and Button.RIGHT in pressed:
                _wait_for_release(hub, wait)
                return
            if Button.LEFT in pressed:
                selected = next_mission_index(selected, -1, len(entries))
                _wait_for_release(hub, wait)
                break
            if Button.RIGHT in pressed:
                selected = next_mission_index(selected, 1, len(entries))
                _wait_for_release(hub, wait)
                break
            if Button.CENTER in pressed:
                _wait_for_release(hub, wait)
                if mission is None:
                    return

                print("OP | Запуск: {}".format(label))
                hub.system.set_stop_button(Button.CENTER)
                try:
                    result = _execute_mission(
                        mission, reset_start, battery_check, MoveError, DEBUG_RAISE
                    )
                finally:
                    _cleanup(hub, Button, rush, stop_all, left_motor, right_motor)

                if result == "ok":
                    print("OP | Готово: {}".format(label))
                else:
                    hub.display.char("!")
                    hub.light.on(Color.RED if result == "failed" else Color.ORANGE)
                    print("OP | Миссия остановлена: {}".format(label))
                wait(500)
                break
            wait(10)


def run_mission_menu(mission_modules, test_modules):
    from core import (
        DEBUG_RAISE,
        MoveError,
        battery_check,
        hub,
        left_motor,
        reset_start,
        right_motor,
        rush,
        stop_all,
    )
    from pybricks.parameters import Button, Color
    from pybricks.tools import wait

    sections = (
        ("Миссии", mission_modules),
        ("Тесты", test_modules),
    )
    selected = 0
    _cleanup(hub, Button, rush, stop_all, left_motor, right_motor)
    _wait_for_release(hub, wait)

    try:
        while True:
            _show_categories(hub, selected, Color)
            while True:
                pressed = hub.buttons.pressed()
                if Button.LEFT in pressed and Button.RIGHT in pressed:
                    _wait_for_release(hub, wait)
                    return
                category = _category_from_button(pressed, Button)
                if category is not None:
                    selected = category
                    _wait_for_release(hub, wait)
                    break
                if Button.CENTER in pressed:
                    _wait_for_release(hub, wait)
                    title, catalog_entries = sections[selected]
                    items = (
                        discover_missions(catalog_entries, Color)
                        if selected == 0
                        else discover_tests(catalog_entries, Color)
                    )
                    _run_section(
                        hub,
                        title,
                        items,
                        Button,
                        Color,
                        wait,
                        reset_start,
                        battery_check,
                        left_motor,
                        right_motor,
                        stop_all,
                        rush,
                        MoveError,
                        DEBUG_RAISE,
                    )
                    break
                wait(10)
    finally:
        # Даже если исключение ушло наверх (DEBUG_RAISE), хаб остаётся в покое.
        _cleanup(hub, Button, rush, stop_all, left_motor, right_motor)
