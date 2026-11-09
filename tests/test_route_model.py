import ast
import unittest

from route_model import (
    generate_pybricks_program,
    route_end_heading_index,
    validate_route_data,
)


class RouteModelTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "version": 1,
            "grid": {"columns": 4, "rows": 4},
            "start": {"x": 1, "y": 2, "heading": "N"},
            "route": [{"x": 1, "y": 2}, {"x": 1, "y": 1}],
        }

    def test_validate_route_data(self):
        self.assertEqual(
            validate_route_data(self.data),
            (4, 4, (1, 2), "N", [(1, 2), (1, 1)]),
        )

    def test_reject_diagonal_route(self):
        self.data["route"].append({"x": 2, "y": 2})
        with self.assertRaises(ValueError):
            validate_route_data(self.data)

    def test_reject_boolean_coordinates(self):
        self.data["start"]["x"] = True
        with self.assertRaises(ValueError):
            validate_route_data(self.data)

    def test_program_is_valid_and_stops_motors(self):
        program = generate_pybricks_program(
            [(1, 2), (1, 3), (2, 3), (2, 2)], "N"
        )
        ast.parse(program)
        self.assertIn("drive_base.turn(90)", program)
        self.assertIn("drive_base.straight(-25)", program)
        self.assertTrue(program.rstrip().endswith("drive_base.stop()"))

    def test_end_heading_accounts_for_backward_motion(self):
        route = [(1, 1), (1, 2), (2, 2)]
        self.assertEqual(route_end_heading_index(route, "N"), 1)


if __name__ == "__main__":
    unittest.main()
