import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidates = self.root / "candidates.json"
        self.history = self.root / "history.json"
        self.output = self.root / "pack.md"
        self.candidates.write_text(json.dumps([
            {"id": "x", "title": "Café", "url": "https://example.org/x", "quality": 8, "relevance": 9}
        ]), encoding="utf-8")
        self.history.write_text("[]", encoding="utf-8")

    def cli(self, *extra, output=None):
        return subprocess.run(
            [sys.executable, "-m", "repeat_resistant_briefs.cli", str(self.candidates),
             str(self.history), str(output or self.output), *extra],
            capture_output=True, text=True, encoding="utf-8", env=os.environ.copy(),
        )

    def test_legacy_invocation_and_utf8(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Café", self.output.read_text(encoding="utf-8"))

    def test_json_and_sidecar_match(self):
        sidecar = self.root / "decisions.json"
        result = self.cli("--format", "json", "--decisions", str(sidecar))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), sidecar.read_bytes())
        report = json.loads(self.output.read_text())
        self.assertEqual(len(report["selected"]), 1)
        self.assertEqual(len(report["decisions"]), 1)

    def test_invalid_inputs_exit_two_without_output(self):
        for document in ("{}", "[null]", "[", '[{"quality": NaN}]', '[{"url":"a","url":"b"}]'):
            self.candidates.write_text(document)
            with self.subTest(document=document):
                result = self.cli()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(self.output.exists())

    def test_invalid_encoding_is_validation_error(self):
        self.candidates.write_bytes(b"\xff")
        result = self.cli()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_input_output_collision_never_overwrites(self):
        before = self.candidates.read_bytes()
        result = self.cli("--overwrite", output=self.candidates)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.candidates.read_bytes(), before)

    def test_sidecar_collision_rejected(self):
        result = self.cli("--decisions", str(self.output))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.output.exists())

    def test_existing_file_requires_explicit_overwrite(self):
        self.output.write_text("keep")
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.output.read_text(), "keep")
        result = self.cli("--overwrite")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Source Pack", self.output.read_text())

    def test_io_error_exit_one(self):
        self.candidates.unlink()
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_strict_floors_and_zero_limit_are_explained(self):
        candidates = json.loads(self.candidates.read_text())
        candidates[0]["quality"] = 5
        self.candidates.write_text(json.dumps(candidates))
        result = self.cli("--strict", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.output.read_text())
        self.assertEqual(report["selected"], [])
        self.assertEqual(len(report["decisions"]), 1)
        result = self.cli("--limit", "0", "--format", "json", "--overwrite")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_text())["selected"], [])

    def test_window_requires_reference_time(self):
        result = self.cli("--window-days", "30")
        self.assertEqual(result.returncode, 2, result.stderr)
        result = self.cli("--window-days", "30", "--as-of", "2026-09-06", "--strict")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
