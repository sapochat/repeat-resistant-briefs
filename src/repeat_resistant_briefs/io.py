"""Small, single-writer file boundary for packs and delivery history.

All destinations are preflighted and staged before publication. Each replacement
is atomic; caught publication failures restore earlier files. This is not a
crash-atomic multi-file transaction and does not coordinate concurrent writers.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Mapping, Iterable


def _same_file(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve() or (
        left.exists() and right.exists() and os.path.samefile(left, right)
    )


def _cleanup(
    paths: Iterable[Path], *, status: str, original: BaseException | None = None
) -> None:
    failures = []
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            failures.append((path, error))
    if failures:
        details = "; ".join(f"{path}: {error}" for path, error in failures)
        primary = f"; primary error: {original}" if original is not None else ""
        raise OSError(
            f"{status}; cleanup failed; leftover paths: {details}{primary}"
        ) from (original if original is not None else failures[0][1])


def _stage(target: Path, data: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return staged
    except BaseException as original:
        _cleanup([staged], status="staging failed; outputs not published", original=original)
        raise


def write_outputs(
    outputs: Mapping[Path, str], *, inputs: Iterable[Path] = (), overwrite: bool = False
) -> None:
    """Write UTF-8 artifacts without aliasing inputs or following symlinks.

    Parent directories must exist. Existing outputs require explicit overwrite.
    Inputs are protected even when overwrite is enabled, including hard links.
    Cleanup errors name leftover paths and distinguish successful publication
    from failure, chaining any primary staging/publication/rollback error.
    """
    targets = [Path(path).absolute() for path in outputs]
    sources = [Path(path).absolute() for path in inputs]
    for index, target in enumerate(targets):
        if any(path.is_symlink() for path in (target, *target.parents)):
            raise ValueError(f"output cannot use symlinks: {target}")
        if any(_same_file(target, source) for source in sources):
            raise ValueError(f"output aliases an input: {target}")
        if any(_same_file(target, previous) for previous in targets[:index]):
            raise ValueError(f"output destinations alias each other: {target}")
        if target.exists():
            if not target.is_file():
                raise ValueError(f"output is not a regular file: {target}")
            if not overwrite:
                raise FileExistsError(f"output exists (use --overwrite): {target}")
        if not target.parent.is_dir():
            raise FileNotFoundError(f"output parent does not exist: {target.parent}")
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    preserve: set[Path] = set()
    primary: BaseException | None = None
    try:
        for target, text in zip(targets, outputs.values()):
            staged[target] = _stage(target, text.encode("utf-8"))
            if target.exists():
                backups[target] = _stage(target, target.read_bytes())
        for target in targets:
            if overwrite:
                os.replace(staged[target], target)
            else:
                # Atomic no-clobber publication, including a late-arriving file.
                os.link(staged[target], target)
            published.append(target)
    except BaseException as original:
        primary = original
        failures = []
        for target in reversed(published):
            try:
                if target in backups:
                    os.replace(backups[target], target)
                else:
                    target.unlink()
            except OSError as error:
                if target in backups:
                    preserve.add(backups[target])
                failures.append(f"{target}: {error}")
        if failures:
            primary = OSError(
                "publication and rollback failed; recover from retained backups "
                f"{sorted(str(p) for p in preserve)}: {'; '.join(failures)}"
            )
            raise primary from original
        raise
    finally:
        _cleanup(
            (path for path in (*staged.values(), *backups.values()) if path not in preserve),
            status="output publication failed" if primary is not None else "outputs successfully published",
            original=primary,
        )
