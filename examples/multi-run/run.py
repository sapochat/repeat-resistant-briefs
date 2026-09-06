#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from repeat_resistant_briefs.briefs import render_source_pack, select_result
from repeat_resistant_briefs.delivery import history_entries, record_delivery
from repeat_resistant_briefs.io import write_outputs


def run(days_path: Path, output: Path, overwrite: bool = False) -> list[dict]:
    """Select independently of delivery; publish only after all days validate.

    Explicit receipts alone advance history. All artifacts are rendered and
    UTF-8 checked before mkdir. The shared single-writer file boundary stages
    publication and rolls back caught write failures, not process crashes.
    Unrelated files are never removed; existing artifacts require opt-in.
    """
    days = json.loads(days_path.read_text(encoding="utf-8"))
    if not isinstance(days, list):
        raise ValueError("days must be a JSON array")

    for index, day in enumerate(days, start=1):
        if not isinstance(day, dict):
            raise ValueError(f"day {index} must be an object")
        day_date = day.get("date")
        if not isinstance(day_date, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day_date):
            raise ValueError(f"day {index}: date must be YYYY-MM-DD")
        try:
            date.fromisoformat(day_date)
        except ValueError as exc:
            raise ValueError(f"day {index}: date must be a valid YYYY-MM-DD date") from exc
        candidates = day.get("candidates")
        if not isinstance(candidates, list) or any(not isinstance(item, dict) for item in candidates):
            raise ValueError(f"day {index}: candidates must be an array of objects")
        if not isinstance(day.get("receipt"), dict):
            raise ValueError(f"day {index}: an explicit receipt object is required")

    history: list | dict = {"schema_version": 1, "entries": [], "receipts": []}
    summary: list[dict] = []
    artifacts: dict[str, str] = {}
    for index, day in enumerate(days, start=1):
        try:
            result = select_result(
                day["candidates"], history_entries(history), limit=8, strict=True,
                min_quality=6, min_relevance=6, profile="conservative",
                as_of=day["date"], window_days=30,
            )
            history = record_delivery(result.to_dict(), history, day["receipt"])
            stem = f"day-{index}-{day['date']}"
            artifacts[stem + ".md"] = render_source_pack(result)
            artifacts[stem + ".selection.json"] = result.to_json() + "\n"
            artifacts[stem + ".receipt.json"] = json.dumps(day["receipt"], indent=2, ensure_ascii=False) + "\n"
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
            raise ValueError(f"day {index}: invalid candidates or receipt: {exc}") from exc
        summary.append({
            "date": day["date"],
            "selected": [item["identity"] for item in result.selected],
            "delivered": [item["identity"] for item in day["receipt"]["items"]],
            "suppressed": [item["identity"] for item in result.decisions if item["disposition"] == "recent_repeat"],
            "source_pack": stem + ".md",
            "selection": stem + ".selection.json",
            "receipt": stem + ".receipt.json",
        })
    artifacts["history.json"] = json.dumps(history, indent=2, ensure_ascii=False) + "\n"
    artifacts["summary.json"] = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"

    # Encoding errors must not create even an empty output directory.
    for content in artifacts.values():
        content.encode("utf-8")

    # Check directories before mkdir; write_outputs owns artifact safety,
    # input-alias protection (including hard links), staging and publication.
    # Do not resolve(): doing so would hide symlinks in ancestor components.
    output = output.absolute()
    for path in (*reversed(output.parents), output):
        if path.is_symlink():
            raise ValueError(f"output path must not contain a symlink: {path}")
        if path.exists() and not path.is_dir():
            raise ValueError(f"output path is not a directory: {path}")
    output.mkdir(parents=True, exist_ok=True)
    write_outputs({output / name: text for name, text in artifacts.items()},
                  inputs=[days_path], overwrite=overwrite)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a three-run repeat-resistance demonstration")
    parser.add_argument("--days", type=Path, default=Path(__file__).with_name("days.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("output"))
    parser.add_argument("--overwrite", action="store_true", help="replace only this run's generated artifacts")
    args = parser.parse_args()
    try:
        summary = run(args.days, args.output, overwrite=args.overwrite)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    for day in summary:
        print(f"{day['date']}: selected={day['selected']} delivered={day['delivered']} suppressed={day['suppressed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
