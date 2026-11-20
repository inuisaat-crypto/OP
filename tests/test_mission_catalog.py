import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


class MissionCatalogTests(unittest.TestCase):
    def test_test_module_is_not_listed_as_a_mission(self):
        modules = {}
        for name in ("mission_1", "mission_2", "system_check"):
            module = ModuleType(name)
            module.NAME = name
            module.COLOR = "CYAN"
            module.run = lambda: None
            modules[name] = module

        catalog_path = Path(__file__).resolve().parents[1] / "mission_catalog.py"
        spec = importlib.util.spec_from_file_location(
            "mission_catalog_under_test", str(catalog_path)
        )
        catalog = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(catalog)

        self.assertEqual(
            [entry[0] for entry in catalog.MISSION_MODULES],
            ["mission_1", "mission_2"],
        )
        self.assertEqual(
            [entry[0] for entry in catalog.TEST_MODULES],
            ["system_check"],
        )


if __name__ == "__main__":
    unittest.main()
