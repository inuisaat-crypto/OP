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


if __name__ == "__main__":
    unittest.main()
