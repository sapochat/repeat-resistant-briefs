"""Offline regression tests for the unpacked-sdist verification boundary."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import venv


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_distribution.py"
SPEC = importlib.util.spec_from_file_location("verify_distribution", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class NestedEnvironmentTests(unittest.TestCase):
    def test_source_verification_from_virtualenv(self):
        # Exercise the same extra venv layer as artifact verification, offline.
        # Select only the source tests so this regression cannot recurse.
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp) / "outer"
            venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(outer)
            python = outer / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            env.pop("PYTHONPATH", None)
            result = subprocess.run(
                [str(python), "-m", "unittest", "-v",
                 "test_distribution_verifier.SourceVerificationTests"],
                cwd=SCRIPT.parent.parent / "tests", env=env,
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Ran 5 tests", result.stderr)


class SourceVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.environment.cleanup)
        root = Path(cls.environment.name)
        venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(root / "venv")
        cls.python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        cls.env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        cls.env.pop("PYTHONPATH", None)
        purelib = subprocess.check_output(
            [str(cls.python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            env=cls.env, text=True,
        ).strip()
        # A directly installed package models an available wheel, without pip/network.
        installed = Path(purelib) / "repeat_resistant_briefs"
        installed.mkdir()
        (installed / "__init__.py").write_text("ORIGIN = 'installed'\n", encoding="utf-8")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        package = self.project / "src/repeat_resistant_briefs"
        package.mkdir(parents=True)
        self.source = package / "__init__.py"
        self.source.write_text("ORIGIN = 'source'\n", encoding="utf-8")
        (self.project / "tests").mkdir()
        self.test_file = self.project / "tests/test_sample.py"
        self.test_file.write_text(
            "import unittest\nimport repeat_resistant_briefs as package\n"
            "class Sample(unittest.TestCase):\n"
            "    def test_source(self): self.assertEqual(package.ORIGIN, 'source')\n",
            encoding="utf-8",
        )

    def verify(self):
        # Capture expected child failures, but still execute the exact command.
        def run(command, **kwargs):
            return subprocess.run(command, **kwargs, check=True, capture_output=True, text=True)

        with patch.object(verifier, "run", side_effect=run):
            verifier.run_source_tests(self.python, self.project, self.env)

    def test_missing_source_rejected_despite_installed_package(self):
        self.source.unlink()
        output = subprocess.check_output(
            [str(self.python), "-c", "import repeat_resistant_briefs as p; print(p.ORIGIN)"],
            cwd=self.project, env=dict(self.env, PYTHONPATH=str(self.project / "src")), text=True,
        )
        self.assertEqual(output.strip(), "installed")
        with self.assertRaisesRegex(ValueError, "source"):
            self.verify()

    def test_import_outside_source_rejected_before_suite(self):
        shadow = self.project / "repeat_resistant_briefs"
        shadow.mkdir()
        (shadow / "__init__.py").write_text("ORIGIN = 'source'\n", encoding="utf-8")
        marker = self.project / "suite-ran"
        self.test_file.write_text(
            "from pathlib import Path\nPath('suite-ran').touch()\n", encoding="utf-8"
        )
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify()
        self.assertFalse(marker.exists())

    def test_source_suite_passes(self):
        self.verify()

    def test_zero_tests_rejected(self):
        self.test_file.unlink()
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify()

    def test_failing_suite_rejected(self):
        self.test_file.write_text(
            "import unittest\nclass Sample(unittest.TestCase):\n"
            "    def test_failure(self): self.fail('intentional regression fixture')\n",
            encoding="utf-8",
        )
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify()
