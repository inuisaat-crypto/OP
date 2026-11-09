import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from route_editor import MIN_CELL_SIZE, RouteEditor


class FakeVariable:
    def __init__(self, value):
        self.value = value

    def get(self):
        if isinstance(self.value, str):
            try:
                return int(self.value)
            except ValueError as error:
                raise tk.TclError(str(error)) from error
        return self.value

    def set(self, value):
        self.value = value


class RouteEditorUiTests(unittest.TestCase):
    def create_editor(self):
        editor = RouteEditor.__new__(RouteEditor)
        editor.columns = FakeVariable(20)
        editor.rows = FakeVariable(14)
        editor.grid_columns = 20
        editor.grid_rows = 14
        editor.start = (1, 1)
        editor.route = [(1, 1), (2, 1), (3, 1)]
        editor.heading = Mock()
        editor.heading.get.return_value = "N"
        editor.route_dirty = False
        editor.route_file_path = None
        editor._fit_grid_to_canvas = Mock()
        editor._draw_grid = Mock()
        editor._update_status = Mock()
        editor._mark_route_dirty = Mock(
            side_effect=lambda: setattr(editor, "route_dirty", True)
        )
        editor._update_window_title = Mock()
        return editor

    def test_grid_size_is_not_applied_until_confirmed(self):
        editor = self.create_editor()
        editor.columns.set(8)
        editor.rows.set(9)

        self.assertEqual(editor._grid_dimensions(), (20, 14))

    def test_invalid_grid_size_is_rejected_and_previous_size_restored(self):
        editor = self.create_editor()
        editor.columns.set("not a number")
        editor.rows.set(101)

        with patch("route_editor.messagebox.showerror") as showerror:
            editor._resize_grid()

        self.assertEqual(editor._grid_dimensions(), (20, 14))
        self.assertEqual(editor.columns.get(), 20)
        self.assertEqual(editor.rows.get(), 14)
        showerror.assert_called_once()
        editor._draw_grid.assert_not_called()

    def test_apply_grid_size_truncates_route_at_new_boundary(self):
        editor = self.create_editor()
        editor.columns.set(2)
        editor.rows.set(4)
        editor._in_bounds = RouteEditor._in_bounds.__get__(editor)

        editor._resize_grid()

        self.assertEqual(editor._grid_dimensions(), (2, 4))
        self.assertEqual(editor.route, [(1, 1)])
        editor._mark_route_dirty.assert_called_once()
        editor._draw_grid.assert_called_once()

    def test_save_uses_applied_size_not_unapplied_spinbox_values(self):
        editor = self.create_editor()
        editor.columns.set(8)
        editor.rows.set(9)
        editor.route = [(1, 1), (2, 1)]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.json"
            self.assertTrue(editor._write_route(str(path)))
            with path.open(encoding="utf-8") as route_file:
                saved = json.load(route_file)

        self.assertEqual(saved["grid"], {"columns": 20, "rows": 14})

    def test_route_launch_requires_a_step_after_start(self):
        editor = self.create_editor()
        editor.ble_connected = True
        editor.ble_running = False
        editor.route = [(1, 1)]
        editor._run_ble_program = Mock()

        with patch("route_editor.messagebox.showerror") as showerror:
            RouteEditor._run_route_over_bluetooth(editor)

        showerror.assert_called_once()
        editor._run_ble_program.assert_not_called()

    def test_large_grid_keeps_cells_clickable_and_uses_scrollregion(self):
        editor = self.create_editor()
        editor.grid_columns = 100
        editor.grid_rows = 14
        editor.cell_size = 42.0
        editor._fit_grid_to_canvas = RouteEditor._fit_grid_to_canvas.__get__(editor)
        editor.canvas = Mock()
        editor.canvas.winfo_width.return_value = 604
        editor.canvas.winfo_height.return_value = 404

        self.assertTrue(editor._fit_grid_to_canvas())

        self.assertEqual(editor.cell_size, MIN_CELL_SIZE)


if __name__ == "__main__":
    unittest.main()
