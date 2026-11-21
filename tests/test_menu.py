import unittest
from unittest.mock import patch

from pybricks_runtime import menu


class _Display:
    def __init__(self):
        self.pixels = {}

    def off(self):
        self.pixels.clear()

    def pixel(self, row, column, brightness):
        self.pixels[(row, column)] = brightness


class _Light:
    def on(self, color):
        self.color = color


class _Hub:
    def __init__(self):
        self.display = _Display()
        self.light = _Light()


class _Color:
    CYAN = "cyan"
    YELLOW = "yellow"


class _Button:
    LEFT = "left"
    RIGHT = "right"


class _System:
    def __init__(self):
        self.stop_button = "preset"

    def set_stop_button(self, value):
        self.stop_button = value


class _MenuHub:
    def __init__(self):
        self.system = _System()


class _Motor:
    def __init__(self):
        self.stops = 0

    def stop(self):
        self.stops += 1


class MenuTests(unittest.TestCase):
    def test_categories_are_stacked_and_top_tile_is_selected(self):
        hub = _Hub()

        with patch("builtins.print"):
            menu._show_categories(hub, 0, _Color)

        bright = {pixel for pixel, value in hub.display.pixels.items() if value == 100}
        dim = {pixel for pixel, value in hub.display.pixels.items() if value == 40}
        self.assertEqual(bright, {(0, 1), (0, 2), (1, 1), (1, 2)})
        self.assertEqual(dim, {(3, 1), (3, 2), (4, 1), (4, 2)})
        self.assertEqual(hub.light.color, _Color.CYAN)

    def test_bottom_tile_can_be_selected(self):
        hub = _Hub()

        with patch("builtins.print"):
            menu._show_categories(hub, 1, _Color)

        bright = {pixel for pixel, value in hub.display.pixels.items() if value == 100}
        self.assertEqual(bright, {(3, 1), (3, 2), (4, 1), (4, 2)})
        self.assertEqual(hub.light.color, _Color.YELLOW)

    def test_two_categories_wrap_in_both_directions(self):
        self.assertEqual(menu.next_mission_index(0, 1, 2), 1)
        self.assertEqual(menu.next_mission_index(1, 1, 2), 0)
        self.assertEqual(menu.next_mission_index(0, -1, 2), 1)

    def test_left_and_right_select_the_two_categories(self):
        self.assertEqual(menu._category_from_button({_Button.LEFT}, _Button), 0)
        self.assertEqual(menu._category_from_button({_Button.RIGHT}, _Button), 1)


    def test_mission_error_is_caught_when_debug_raise_is_off(self):
        calls = []

        def mission():
            raise ValueError("boom")

        with patch("builtins.print"):
            result = menu._execute_mission(
                mission,
                lambda: calls.append("reset"),
                lambda: calls.append("battery"),
                RuntimeError,
                False,
            )

        self.assertEqual(result, "failed")
        self.assertEqual(calls, ["reset", "battery"])

    def test_mission_error_is_reraised_when_debug_raise_is_on(self):
        def mission():
            raise ValueError("boom")

        with patch("builtins.print"):
            with self.assertRaises(ValueError):
                menu._execute_mission(
                    mission, lambda: None, lambda: None, RuntimeError, True
                )

    def test_system_exit_is_reported_as_stopped(self):
        def mission():
            raise SystemExit

        with patch("builtins.print"):
            result = menu._execute_mission(
                mission, lambda: None, lambda: None, RuntimeError, False
            )

        self.assertEqual(result, "stopped")

    def test_move_error_is_reported_as_failed(self):
        class MoveError(Exception):
            pass

        def mission():
            raise MoveError("упор")

        with patch("builtins.print"):
            result = menu._execute_mission(
                mission, lambda: None, lambda: None, MoveError, False
            )

        self.assertEqual(result, "failed")

    def test_cleanup_restores_hub_state(self):
        hub = _MenuHub()
        left, right = _Motor(), _Motor()
        rush_values = []
        stopped = []

        menu._cleanup(
            hub, _Button, rush_values.append, lambda: stopped.append("all"), left, right
        )

        self.assertEqual(rush_values, [False])
        self.assertEqual(stopped, ["all"])
        self.assertEqual((left.stops, right.stops), (1, 1))
        self.assertIsNone(hub.system.stop_button)


if __name__ == "__main__":
    unittest.main()
