#!/usr/bin/env python3
"""Exercise built artifacts outside the checkout; run after `python -m build`."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def run_source_tests(python: Path, project: Path, env: dict[str, str]) -> dict[str, str]:
    """Require real sdist imports and a nonempty, successful source test suite."""
    source = project.resolve() / "src"
    initializer = source / "repeat_resistant_briefs/__init__.py"
    if not initializer.is_file():
        raise ValueError("sdist missing package source: " + str(initializer))
    source_env = dict(env, PYTHONPATH=str(source))
    code = """
import sys
import unittest
from pathlib import Path
import repeat_resistant_briefs
expected = Path(sys.argv[1]).resolve()
actual = Path(repeat_resistant_briefs.__file__).resolve()
if actual != expected:
    sys.exit(f"sdist import must use {expected}, got {actual}")
suite = unittest.defaultTestLoader.discover('tests')
if suite.countTestCases() == 0:
    sys.exit('sdist test suite is empty')
sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
"""
    run([str(python), "-c", code, str(initializer)], cwd=project, env=source_env)
    return source_env


def verify(dist: Path) -> None:
    wheels = sorted(dist.glob("*.whl"))
    sources = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("distribution directory must contain exactly one wheel and one sdist")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="rrb-distribution-") as tmp:
        root = Path(tmp)
        unpacked = root / "sdist"
        unpacked.mkdir()
        with tarfile.open(sources[0]) as archive:
            for member in archive.getmembers():
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                    raise ValueError(f"unsafe sdist member: {member.name}")
            if hasattr(tarfile, "data_filter"):
                archive.extractall(unpacked, filter="data")
            else:
                archive.extractall(unpacked)
        projects = list(unpacked.iterdir())
        if len(projects) != 1 or not projects[0].is_dir():
            raise ValueError("sdist must contain one project directory")
        project = projects[0]
        assert (project / "examples/multi-run/days.json").is_file(), "sdist missing example fixtures"
        assert (project / "SKILL.md").is_file(), "sdist missing portable skill"
        virtualenv = root / "venv"
        # Copied relocatable POSIX interpreters can lose their stdlib when nested.
        venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(virtualenv)
        bindir = virtualenv / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        cli = bindir / ("repeat-resistant-briefs.exe" if os.name == "nt" else "repeat-resistant-briefs")
        run([str(python), "-m", "pip", "install", "--no-deps", str(wheels[0].resolve())], cwd=root, env=env)
        # Both imports and the entry point must work without the source tree on sys.path.
        run([str(python), "-c", "import repeat_resistant_briefs; print(repeat_resistant_briefs.__file__)"], cwd=root, env=env)
        examples = root / "examples"
        shutil.copytree(project / "examples", examples)
        wheel_pack = root / "wheel-pack.md"
        args = [str(examples / "candidates.json"), str(examples / "history.json")]
        run([str(cli), *args, str(wheel_pack)], cwd=root, env=env)
        text = wheel_pack.read_text(encoding="utf-8")
        assert text.startswith("# Source Pack\n"), "installed CLI did not generate a source pack"
        assert "A New Context Method" in text and "FOLLOW-UP" in text, "installed CLI lost sample selections"
        # Execute the included tests against the unpacked source, not the checkout.
        source_env = run_source_tests(python, project, env)
        source_pack = root / "source-pack.md"
        run([str(python), "-m", "repeat_resistant_briefs.cli", *args, str(source_pack)], cwd=project, env=source_env)
        assert wheel_pack.read_bytes() == source_pack.read_bytes(), "wheel and sdist outputs differ"
        demo = root / "demo"
        run([str(python), str(project / "examples/multi-run/run.py"), "--output", str(demo)], cwd=root, env=env)
        golden = project / "examples/multi-run/output"
        expected = {p.name for p in golden.iterdir() if p.is_file()}
        actual = {p.name for p in demo.iterdir() if p.is_file()}
        assert actual == expected, f"demo artifacts differ: {actual ^ expected}"
        for name in sorted(expected):
            assert (demo / name).read_bytes() == (golden / name).read_bytes(), f"demo golden differs: {name}"
        print("PASS: isolated wheel, unpacked sdist tests, CLI parity, and demo goldens", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    verify(args.dist.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
