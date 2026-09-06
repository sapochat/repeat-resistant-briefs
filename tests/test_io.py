import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repeat_resistant_briefs import io as file_io


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_writes_utf8_outputs(self):
        target = self.root / "pack.md"
        file_io.write_outputs({target: "café\n"})
        self.assertEqual(target.read_text(encoding="utf-8"), "café\n")

    def test_existing_file_requires_overwrite(self):
        target = self.root / "pack.md"
        target.write_text("old")
        with self.assertRaises(FileExistsError):
            file_io.write_outputs({target: "new"})
        self.assertEqual(target.read_text(), "old")
        file_io.write_outputs({target: "new"}, overwrite=True)
        self.assertEqual(target.read_text(), "new")

    def test_all_destinations_checked_before_writing(self):
        first, second = self.root / "a", self.root / "b"
        second.write_text("old")
        with self.assertRaises(FileExistsError):
            file_io.write_outputs({first: "new", second: "new"})
        self.assertFalse(first.exists())
        self.assertEqual(second.read_text(), "old")

    def test_input_aliases_rejected_even_with_overwrite(self):
        source = self.root / "source"
        source.write_text("input")
        alias = self.root / "hardlink"
        os.link(source, alias)
        for target in (source, alias):
            with self.subTest(target=target), self.assertRaises(ValueError):
                file_io.write_outputs({target: "bad"}, inputs=[source], overwrite=True)
        self.assertEqual(source.read_text(), "input")

    def test_duplicate_resolved_outputs_rejected(self):
        target = self.root / "a"
        duplicate = self.root / "sub" / ".." / "a"
        with self.assertRaises(ValueError):
            file_io.write_outputs({target: "x", duplicate: "y"})
        self.assertFalse(target.exists())

    def test_symlink_target_and_parent_rejected(self):
        source = self.root / "source"
        source.write_text("old")
        link = self.root / "link"
        link.symlink_to(source)
        directory = self.root / "dir"
        directory.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        for target in (link, alias / "new"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                file_io.write_outputs({target: "bad"}, overwrite=True)
        self.assertEqual(source.read_text(), "old")
        self.assertFalse((directory / "new").exists())

    def test_failed_stage_does_not_modify_existing_output(self):
        target = self.root / "pack"
        target.write_text("old")
        with patch.object(file_io.tempfile, "mkstemp", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                file_io.write_outputs({target: "new"}, overwrite=True)
        self.assertEqual(target.read_text(), "old")

    def test_publish_failure_rolls_back_prior_outputs(self):
        first, second = self.root / "a", self.root / "b"
        first.write_text("old-a")
        second.write_text("old-b")
        replace = os.replace
        calls = 0

        def fail_second(src, dst):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("publish failure")
            return replace(src, dst)

        with patch.object(file_io.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                file_io.write_outputs({first: "new-a", second: "new-b"}, overwrite=True)
        self.assertEqual(first.read_text(), "old-a")
        self.assertEqual(second.read_text(), "old-b")
        self.assertEqual({p.name for p in self.root.iterdir()}, {"a", "b"})

    def test_published_outputs_cleanup_attempts_every_staging_path(self):
        first, second = self.root / "a", self.root / "b"
        unlink = Path.unlink
        attempted = []
        denied = PermissionError("cleanup denied")

        def fail_first(path, *args, **kwargs):
            attempted.append(path)
            if len(attempted) == 1:
                raise denied
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", fail_first):
            with self.assertRaises(OSError) as caught:
                file_io.write_outputs({first: "new-a", second: "new-b"})
        self.assertEqual(len(attempted), 2)
        self.assertTrue(attempted[0].exists())
        self.assertFalse(attempted[1].exists())
        self.assertEqual(first.read_text(), "new-a")
        self.assertEqual(second.read_text(), "new-b")
        self.assertIn("outputs successfully published; cleanup failed", str(caught.exception))
        self.assertIn(str(attempted[0]), str(caught.exception))
        self.assertNotIn(str(attempted[1]), str(caught.exception))
        self.assertIs(caught.exception.__cause__, denied)

    def test_publication_cleanup_failure_preserves_primary(self):
        first, second = self.root / "a", self.root / "b"
        unlink, link = Path.unlink, os.link
        attempted = []
        original = OSError("publish failure")

        def fail_second(src, dst):
            if dst == second:
                raise original
            return link(src, dst)

        def deny_first_stage(path, *args, **kwargs):
            if path.suffix == ".tmp":
                attempted.append(path)
                if len(attempted) == 1:
                    raise PermissionError("cleanup denied")
            return unlink(path, *args, **kwargs)

        with patch.object(file_io.os, "link", fail_second), patch.object(Path, "unlink", deny_first_stage):
            with self.assertRaises(OSError) as caught:
                file_io.write_outputs({first: "new-a", second: "new-b"})
        self.assertEqual(len(attempted), 2)
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
        self.assertFalse(attempted[1].exists())
        self.assertIs(caught.exception.__cause__, original)
        self.assertIn("publication failed", str(caught.exception))
        self.assertIn("publish failure", str(caught.exception))
        self.assertIn(str(attempted[0]), str(caught.exception))

    def test_rollback_cleanup_failure_retains_recovery_backup(self):
        first, second = self.root / "a", self.root / "b"
        first.write_text("old-a")
        second.write_text("old-b")
        stage, replace, unlink = file_io._stage, os.replace, Path.unlink
        staged, attempted = [], []
        original = OSError("publish failure")
        replacements = 0

        def track_stage(target, data):
            path = stage(target, data)
            staged.append(path)
            return path

        def fail_publish_and_rollback(src, dst):
            nonlocal replacements
            replacements += 1
            if replacements == 2:
                raise original
            if replacements == 3:
                raise OSError("rollback denied")
            return replace(src, dst)

        def deny_second_stage(path, *args, **kwargs):
            attempted.append(path)
            if path == staged[2]:
                raise PermissionError("cleanup denied")
            return unlink(path, *args, **kwargs)

        with patch.object(file_io, "_stage", track_stage), patch.object(file_io.os, "replace", fail_publish_and_rollback), patch.object(Path, "unlink", deny_second_stage):
            with self.assertRaises(OSError) as caught:
                file_io.write_outputs({first: "new-a", second: "new-b"}, overwrite=True)
        self.assertEqual(set(attempted), {staged[0], staged[2], staged[3]})
        self.assertEqual(staged[1].read_text(), "old-a")
        self.assertFalse(staged[3].exists())
        self.assertTrue(staged[2].exists())
        self.assertEqual(first.read_text(), "new-a")
        self.assertEqual(second.read_text(), "old-b")
        self.assertIn("rollback failed", str(caught.exception))
        self.assertIn("rollback denied", str(caught.exception))
        self.assertIn(str(staged[1]), str(caught.exception))
        self.assertIn(str(staged[2]), str(caught.exception))
        rollback_error = caught.exception.__cause__
        assert rollback_error is not None
        self.assertIs(rollback_error.__cause__, original)

    def test_stage_cleanup_failure_preserves_disk_write_failure(self):
        first, second = self.root / "a", self.root / "b"
        fsync, unlink = os.fsync, Path.unlink
        syncs = 0
        leftovers = []
        original = OSError("disk full")

        def fail_second_sync(fd):
            nonlocal syncs
            syncs += 1
            if syncs == 2:
                raise original
            return fsync(fd)

        def deny_failed_stage(path, *args, **kwargs):
            if path.name.startswith(".b."):
                leftovers.append(path)
                raise PermissionError("cleanup denied")
            return unlink(path, *args, **kwargs)

        with patch.object(file_io.os, "fsync", fail_second_sync), patch.object(Path, "unlink", deny_failed_stage):
            with self.assertRaises(OSError) as caught:
                file_io.write_outputs({first: "new-a", second: "new-b"})
        self.assertEqual(set(self.root.iterdir()), set(leftovers))
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
        self.assertIs(caught.exception.__cause__, original)
        self.assertIn("staging failed", str(caught.exception))
        self.assertIn("disk full", str(caught.exception))
        self.assertIn(str(leftovers[0]), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
