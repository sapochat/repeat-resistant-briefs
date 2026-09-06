import importlib.util
import json
import tempfile
import subprocess
import sys
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

    def test_omitted_selection_remains_eligible_and_event_replay_is_suppressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            summary = MODULE.run(SCRIPT.parent / "days.json", output)
            self.assertEqual(summary[0]["delivered"], ["signal:alpha", "signal:beta"])
            self.assertIn("signal:gamma", summary[1]["selected"])
            self.assertEqual(summary[1]["delivered"], ["signal:gamma", "signal:beta", "signal:delta"])
            self.assertEqual(summary[2]["delivered"], ["signal:epsilon"])
            selection = json.loads((output / summary[2]["selection"]).read_text())
            beta = next(row for row in selection["decisions"] if row["identity"] == "signal:beta")
            self.assertEqual(beta["disposition"], "recent_repeat")
            self.assertEqual(beta["code"], "event_already_delivered")
            for day in summary:
                artifact = json.loads((output / day["selection"]).read_text())
                policy = artifact["policy"]
                self.assertTrue(policy["strict"])
                self.assertEqual(policy["window_days"], 30)
                self.assertEqual(policy["min_quality"], 6)
                self.assertEqual(policy["min_relevance"], 6)
                self.assertTrue(policy["as_of"].startswith(day["date"]))
            history = json.loads((output / "history.json").read_text())
            self.assertEqual(len(history["entries"]), 6)
            self.assertEqual(len(history["receipts"]), 3)
            self.assertNotIn("signal:gamma", [row["identity"] for row in history["entries"]
                                            if row["report_id"] == "demo-day-1"])

    def test_late_receipt_and_encoding_failures_do_not_change_filesystem(self):
        for invalid in ("absent", "unknown", "surrogate"):
            for exists in (False, True):
                with self.subTest(invalid=invalid, exists=exists), tempfile.TemporaryDirectory() as tmp:
                    days = self.fixture_days()
                    if invalid == "absent":
                        days[-1].pop("receipt", None)
                    elif invalid == "unknown":
                        days[-1]["receipt"] = {"report_id": "bad", "delivered_at": days[-1]["date"],
                                               "items": [{"identity": "signal:unknown"}]}
                    else:
                        days[-1]["candidates"][-1]["title"] = "bad\ud800"
                    path = Path(tmp) / "days.json"
                    path.write_text(json.dumps(days))
                    output = Path(tmp) / "missing" / "output"
                    if exists:
                        MODULE.run(SCRIPT.parent / "days.json", output)
                        (output / "sentinel").write_text("keep")
                    before = self.snapshot(Path(tmp))
                    with self.assertRaises(ValueError):
                        MODULE.run(path, output, overwrite=True)
                    self.assertEqual(self.snapshot(Path(tmp)), before)
                    self.assertEqual(output.parent.exists(), exists)

    def test_days_input_protected_even_with_overwrite(self):
        for hardlink in (False, True):
            with self.subTest(hardlink=hardlink), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp)
                path = output / "summary.json"
                path.write_text(json.dumps(self.fixture_days()))
                source = path
                if hardlink:
                    source = output / "days.json"
                    source.hardlink_to(path)
                before = self.snapshot(output)
                with self.assertRaisesRegex(ValueError, "input"):
                    MODULE.run(source, output, overwrite=True)
                self.assertEqual(self.snapshot(output), before)

    def test_golden_exact_artifact_set_and_bytes(self):
        expected_names = {"summary.json", "history.json"}
        for i, day in enumerate(self.fixture_days(), 1):
            stem = f"day-{i}-{day['date']}"
            expected_names.update({stem + ".md", stem + ".selection.json", stem + ".receipt.json"})
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            MODULE.run(SCRIPT.parent / "days.json", output)
            actual = self.snapshot(output)
            self.assertEqual(set(actual), expected_names)
            self.assertEqual(actual, self.snapshot(SCRIPT.parent / "output"))

    def test_readme_delivery_receipt_matches_legacy_sample_selection(self):
        from repeat_resistant_briefs.briefs import select_result
        from repeat_resistant_briefs.delivery import record_delivery
        candidates = json.loads((ROOT / "examples/candidates.json").read_text())
        history = json.loads((ROOT / "examples/history.json").read_text())
        receipt_path = ROOT / "examples/delivery-receipt.json"
        self.assertTrue(receipt_path.is_file(), "README sample needs an explicit receipt")
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["items"], [{"identity": "paper:new-context"}, {"identity": "repo:openhuman"}])
        result = select_result(candidates, history, strict=False, min_quality=0, min_relevance=0, profile="legacy")
        delivered = record_delivery(result.to_dict(), history, receipt)
        self.assertEqual(len(delivered["entries"]), len(history) + 2)

    def fixture_days(self):
        return json.loads((SCRIPT.parent / "days.json").read_text())

    def snapshot(self, root):
        return {str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def test_preserves_unrelated_files_and_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            (output / "notes").mkdir(parents=True)
            sentinel = output / "notes" / "keep.txt"
            sentinel.write_text("irreplaceable")
            MODULE.run(SCRIPT.parent / "days.json", output)
            self.assertEqual(sentinel.read_text(), "irreplaceable")

    def test_conflicting_owned_artifacts_refuse_before_any_write(self):
        for name in ("summary.json", "day-3-2026-07-22.md"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "output"
                output.mkdir()
                (output / name).write_text("existing")
                before = self.snapshot(output)
                with self.assertRaisesRegex(FileExistsError, "overwrite"):
                    MODULE.run(SCRIPT.parent / "days.json", output)
                self.assertEqual(self.snapshot(output), before)

    def test_overwrite_changes_only_current_owned_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            output.mkdir()
            (output / "summary.json").write_text("old summary")
            (output / "day-1-2026-07-20.md").write_text("old pack")
            (output / "day-99-2020-01-01.md").write_text("not this run")
            (output / "notes").mkdir()
            (output / "notes" / "keep.txt").write_text("keep")
            summary = MODULE.run(SCRIPT.parent / "days.json", output, overwrite=True)
            self.assertEqual(json.loads((output / "summary.json").read_text()), summary)
            self.assertTrue((output / summary[0]["source_pack"]).read_text().startswith("# Source Pack"))
            self.assertEqual((output / "day-99-2020-01-01.md").read_text(), "not this run")
            self.assertEqual((output / "notes" / "keep.txt").read_text(), "keep")

    def test_invalid_full_days_input_leaves_existing_output_untouched(self):
        invalid = [None, {}, "days", [None], [{"date": "2026-07-20"}],
                   [{"date": "2026-07-20", "candidates": {}}],
                   [{"date": "2026-07-20", "candidates": [None]}]]
        for value in invalid:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                days = Path(tmp) / "days.json"
                days.write_text(json.dumps(value))
                output = Path(tmp) / "output"
                output.mkdir()
                (output / "sentinel").write_text("keep")
                before = self.snapshot(output)
                with self.assertRaises(ValueError):
                    MODULE.run(days, output)
                self.assertEqual(self.snapshot(output), before)

    def test_invalid_dates_rejected_before_creating_output(self):
        for date in ("2026-7-20", "2026-02-30", "20260720", "../escape", "x/../../escape",
                     "2026-07-20/../../escape", "2026-07-20\n", "２０２６-０７-２０", None, 20260720):
            with self.subTest(date=date), tempfile.TemporaryDirectory() as tmp:
                days = self.fixture_days()
                days[-1]["date"] = date
                path = Path(tmp) / "days.json"
                path.write_text(json.dumps(days))
                output = Path(tmp) / "missing" / "output"
                with self.assertRaises(ValueError):
                    MODULE.run(path, output)
                self.assertFalse(output.parent.exists())
                self.assertEqual(set(self.snapshot(Path(tmp))), {"days.json"})

    def test_late_invalid_candidate_is_rendered_before_any_write(self):
        for exists in (False, True):
            with self.subTest(exists=exists), tempfile.TemporaryDirectory() as tmp:
                days = self.fixture_days()
                del days[-1]["candidates"][-1]["title"]
                path = Path(tmp) / "days.json"
                path.write_text(json.dumps(days))
                output = Path(tmp) / "output"
                if exists:
                    output.mkdir()
                    (output / "summary.json").write_text("old summary")
                    (output / "sentinel").write_text("keep")
                before = self.snapshot(Path(tmp))
                with self.assertRaises(ValueError):
                    MODULE.run(path, output, overwrite=True)
                self.assertEqual(self.snapshot(Path(tmp)), before)
                self.assertEqual(output.exists(), exists)

    def test_output_symlinks_are_rejected_without_touching_targets(self):
        for nested in (False, True):
            with self.subTest(nested=nested), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "target"
                target.mkdir()
                (target / "sentinel").write_text("keep")
                link = Path(tmp) / "link"
                link.symlink_to(target, target_is_directory=True)
                output = link / "output" if nested else link
                with self.assertRaisesRegex(ValueError, "symlink"):
                    MODULE.run(SCRIPT.parent / "days.json", output, overwrite=True)
                self.assertTrue(link.is_symlink())
                self.assertEqual(self.snapshot(target), {"sentinel": b"keep"})

    def test_generated_symlinks_are_rejected_including_dangling_links(self):
        for name in ("summary.json", "day-3-2026-07-22.md"):
            for dangling in (False, True):
                with self.subTest(name=name, dangling=dangling), tempfile.TemporaryDirectory() as tmp:
                    output = Path(tmp) / "output"
                    output.mkdir()
                    target = Path(tmp) / "unrelated"
                    if not dangling:
                        target.write_text("keep")
                    (output / name).symlink_to(target)
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        MODULE.run(SCRIPT.parent / "days.json", output, overwrite=True)
                    self.assertTrue((output / name).is_symlink())
                    self.assertEqual(list(output.iterdir()), [output / name])
                    self.assertEqual(target.exists(), not dangling)
                    if not dangling:
                        self.assertEqual(target.read_text(), "keep")

    def test_owned_directory_conflict_never_deleted_even_with_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            conflict = output / "summary.json"
            conflict.mkdir(parents=True)
            (conflict / "sentinel").write_text("keep")
            with self.assertRaises((ValueError, FileExistsError)):
                MODULE.run(SCRIPT.parent / "days.json", output, overwrite=True)
            self.assertEqual(self.snapshot(output), {"summary.json/sentinel": b"keep"})

    def test_cli_default_refuses_populated_committed_output(self):
        # Copy the committed default layout: a regression must not rewrite it.
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "run.py"
            script.write_bytes(SCRIPT.read_bytes())
            (script.parent / "days.json").write_bytes((SCRIPT.parent / "days.json").read_bytes())
            output = script.parent / "output"
            output.mkdir()
            for name, content in self.snapshot(SCRIPT.parent / "output").items():
                (output / name).write_bytes(content)
            before = self.snapshot(output)
            result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--overwrite", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(self.snapshot(output), before)

    def test_cli_overwrite_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            output.mkdir()
            (output / "summary.json").write_text("old")
            result = subprocess.run([sys.executable, str(SCRIPT), "--output", str(output), "--overwrite"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads((output / "summary.json").read_text())), 3)


if __name__ == "__main__":
    unittest.main()
