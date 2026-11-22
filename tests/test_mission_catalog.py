import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from build_archive import _render_catalog


class MissionCatalogTests(unittest.TestCase):
    def test_source_catalog_registers_only_tests(self):
        module = ModuleType("system_check")
        module.NAME = "system_check"
        module.COLOR = "CYAN"
        module.run = lambda: None

        catalog_path = Path(__file__).resolve().parents[1] / "mission_catalog.py"
        spec = importlib.util.spec_from_file_location(
            "mission_catalog_under_test", str(catalog_path)
        )
        catalog = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"system_check": module}):
            spec.loader.exec_module(catalog)

        self.assertEqual(catalog.MISSION_MODULES, ())
        self.assertEqual(
            [entry[0] for entry in catalog.TEST_MODULES],
            ["system_check"],
        )

    def test_json_missions_are_added_to_the_archive_catalog(self):
        catalog_path = Path(__file__).resolve().parents[1] / "mission_catalog.py"
        source = catalog_path.read_text(encoding="utf-8")

        rendered = _render_catalog(source, ["mission_1", "mission_2"])

        for name in ("mission_1", "mission_2"):
            self.assertIn("from {} import (".format(name), rendered)
            self.assertIn(
                "({!r}, _{}_name, _{}_run, _{}_color),".format(
                    name, name, name, name
                ),
                rendered,
            )
        compile(rendered, "mission_catalog.py", "exec")


if __name__ == "__main__":
    unittest.main()
