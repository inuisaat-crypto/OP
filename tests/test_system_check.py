import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


class SystemCheckTests(unittest.TestCase):
    def test_square_attachment_sweeps_and_beep_run_in_order(self):
        events = []
        left = object()
        right = object()
        coast = object()

        fake_core = ModuleType("core")
        fake_core.MoveError = type("MoveError", (Exception,), {})
        fake_core.att_left = left
        fake_core.att_right = right
        fake_core.att_run = lambda motor, speed, angle, then: (
            events.append(("attachment", motor, speed, angle, then)) or True
        )
        fake_core.straight = lambda distance, speed: (
            events.append(("straight", distance, speed)) or True
        )
        fake_core.turn = lambda angle, rate: (
            events.append(("turn", angle, rate)) or True
        )
        fake_core.hub = SimpleNamespace(
            speaker=SimpleNamespace(
                beep=lambda frequency, duration: events.append(
                    ("beep", frequency, duration)
                )
            )
        )

        fake_pybricks = ModuleType("pybricks")
        fake_pybricks.__path__ = []
        fake_parameters = ModuleType("pybricks.parameters")
        fake_parameters.Stop = SimpleNamespace(COAST=coast)
        fake_tools = ModuleType("pybricks.tools")
        fake_tools.wait = Mock()
        module_path = Path(__file__).resolve().parents[1] / "system_check.py"
        spec = importlib.util.spec_from_file_location(
            "system_check_under_test", str(module_path)
        )
        module = importlib.util.module_from_spec(spec)

        replacements = {
            "core": fake_core,
            "pybricks": fake_pybricks,
            "pybricks.parameters": fake_parameters,
            "pybricks.tools": fake_tools,
        }
        with patch.dict(sys.modules, replacements):
            spec.loader.exec_module(module)
            module.run()

        self.assertEqual(
            [event[0] for event in events],
            ["straight", "turn"] * 4 + ["attachment"] * 4 + ["beep"],
        )
        attachment_angles = [
            (event[1], event[3])
            for event in events
            if event[0] == "attachment"
        ]
        self.assertEqual(
            attachment_angles,
            [(left, 45), (left, -45), (right, 45), (right, -45)],
        )


if __name__ == "__main__":
    unittest.main()
