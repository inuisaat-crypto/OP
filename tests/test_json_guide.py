import json
import re
import unittest
from pathlib import Path

from mission_format import STEP_TYPES, validate_mission
from mission_tester import discover_missions


class JsonGuideTests(unittest.TestCase):
    def test_markdown_guide_documents_commands_and_has_valid_example(self):
        root = Path(__file__).resolve().parents[1]
        guide_path = root / "JSON_GUIDE.md"
        guide = guide_path.read_text(encoding="utf-8")

        for step_type in STEP_TYPES:
            self.assertIn("`{}`".format(step_type), guide)
        examples = re.findall(r"```json\s+(.*?)\s+```", guide, re.DOTALL)
        self.assertTrue(examples)
        validate_mission(json.loads(examples[-1]))
        self.assertNotIn(
            guide_path.resolve(),
            [path.resolve() for path in discover_missions()],
        )


if __name__ == "__main__":
    unittest.main()
