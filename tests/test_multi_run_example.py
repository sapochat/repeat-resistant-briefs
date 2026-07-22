import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "examples/multi-run/run.py"
SPEC = importlib.util.spec_from_file_location("multi_run", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load multi-run example: {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MultiRunExampleTests(unittest.TestCase):
    def test_history_suppresses_repeats_but_allows_material_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = MODULE.run(ROOT / "examples/multi-run/days.json", Path(tmp) / "output")
        self.assertEqual(summary[0]["selected"], ["signal:alpha", "signal:beta", "signal:gamma"])
        self.assertIn("signal:alpha", summary[1]["suppressed"])
        self.assertIn("signal:beta", summary[1]["selected"])
        self.assertIn("signal:beta", summary[2]["suppressed"])
        self.assertEqual(summary[2]["selected"], ["signal:epsilon"])


if __name__ == "__main__":
    unittest.main()
