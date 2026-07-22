#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from repeat_resistant_briefs.briefs import build_source_pack, select_candidates


def run(days_path: Path, output: Path) -> list[dict]:
    days = json.loads(days_path.read_text())
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    history: list[dict] = []
    summary: list[dict] = []
    for index, day in enumerate(days, start=1):
        selected, suppressed = select_candidates(day["candidates"], history, limit=8)
        pack = build_source_pack(day["candidates"], history, limit=8)
        filename = f"day-{index}-{day['date']}.md"
        (output / filename).write_text(pack)
        summary.append({
            "date": day["date"],
            "selected": [item["identity"] for item in selected],
            "suppressed": [item["identity"] for item in suppressed],
            "source_pack": filename,
        })
        history.extend({"id": item["identity"], "url": item["canonical_url"], "delivered_at": day["date"]} for item in selected)

    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a three-run repeat-resistance demonstration")
    parser.add_argument("--days", type=Path, default=Path(__file__).with_name("days.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("output"))
    args = parser.parse_args()
    summary = run(args.days, args.output)
    for day in summary:
        print(f"{day['date']}: selected={day['selected']} suppressed={day['suppressed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
