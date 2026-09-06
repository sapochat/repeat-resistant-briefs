import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from repeat_resistant_briefs.briefs import select_result


class DeliveryCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.history = self.root / "history.json"
        self.history.write_text("[]")
        self.selection = self.root / "selection.json"
        candidate = {"id": "x", "title": "X", "url": "https://example.org/x", "quality": 8, "relevance": 8}
        self.selection.write_text(select_result([candidate], [], as_of="2026-09-06").to_json())
        self.receipt = self.root / "receipt.json"
        self.receipt.write_text(json.dumps({"report_id": "brief-1", "delivered_at": "2026-09-06", "items": [{"identity": "x"}]}))
        self.output = self.root / "next-history.json"

    def call(self, history=None, output=None, extra=()):
        return subprocess.run([sys.executable, "-m", "repeat_resistant_briefs.cli", "record-delivery", str(self.selection), str(history or self.history), str(self.receipt), str(output or self.output), *extra], capture_output=True, text=True, env=os.environ.copy())

    def test_record_and_replay_and_next_selection(self):
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.output.read_text())
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(self.history.read_text(), "[]")
        replay = self.root / "replayed.json"
        result = self.call(history=self.output, output=replay)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(replay.read_text()), data)
        candidates = self.root / "candidates.json"
        candidates.write_text(json.dumps([{"id":"x", "title":"X", "url":"https://example.org/x", "quality":8, "relevance":8}]))
        pack = self.root / "next-pack.json"
        result = subprocess.run([sys.executable,"-m","repeat_resistant_briefs.cli",str(candidates),str(replay),str(pack),"--strict","--format","json","--as-of","2026-09-07","--window-days","30"],capture_output=True,text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(pack.read_text())["selected"], [])

    def test_typed_collision_records_both_and_replays_byte_identically(self):
        text = 'https://example.org/shared'
        rows = [dict(id=text, title='ID', url='https://example.org/other', quality=9, relevance=9),
                dict(title='URL', url=text, quality=9, relevance=9)]
        self.selection.write_text(select_result(rows, [], as_of='2026-09-06').to_json())
        ack = dict(report_id='collision', delivered_at='2026-09-06', items=[dict(identity=text)])
        self.receipt.write_text(json.dumps(ack))
        result = self.call()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('supply identity_type', result.stderr)
        self.assertFalse(self.output.exists())
        ack['items'] = [dict(identity=text, identity_type=kind) for kind in ('id', 'url')]
        self.receipt.write_text(json.dumps(ack))
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.output.read_text())
        self.assertEqual(len(data['entries']), 2)
        replay = self.root / 'replay.json'
        result = self.call(history=self.output, output=replay)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(replay.read_bytes(), self.output.read_bytes())
        from repeat_resistant_briefs.delivery import history_entries
        self.assertEqual(select_result(rows, history_entries(data), as_of='2026-09-07').selected, [])

    def test_unknown_item_does_not_write(self):
        data = json.loads(self.receipt.read_text())
        data["items"] = [{"identity":"not-selected"}]
        self.receipt.write_text(json.dumps(data))
        result = self.call()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.output.exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_history_alias_rejected_even_with_overwrite(self):
        result = self.call(output=self.history, extra=("--overwrite",))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.history.read_text(), "[]")


if __name__ == "__main__":
    unittest.main()
