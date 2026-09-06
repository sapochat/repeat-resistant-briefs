"""Command-line boundary: validate, select once, then safely publish artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .briefs import select_result
from .io import write_outputs
from .validation import load_json, stable_json


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a history-aware source pack without changing delivery history.",
        epilog="Record actual delivery separately: repeat-resistant-briefs record-delivery --help",
    )
    parser.add_argument("candidates", type=Path)
    parser.add_argument("history", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--strict", action="store_true", help="require scores and structured follow-ups; default floors 6/10")
    parser.add_argument("--min-quality", type=float)
    parser.add_argument("--min-relevance", type=float)
    parser.add_argument("--canonicalization", choices=("conservative", "legacy"), help="default: conservative with --strict, legacy otherwise")
    parser.add_argument("--window-days", type=int, help="inclusive delivery window; requires --as-of")
    parser.add_argument("--as-of", help="explicit ISO date or timezone-aware timestamp")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--decisions", type=Path, help="also save the same selection result as JSON")
    parser.add_argument("--overwrite", action="store_true", help="replace outputs, never inputs")
    return parser


def _build(args: argparse.Namespace) -> None:
    from .briefs import render_source_pack

    candidates, history = load_json(args.candidates), load_json(args.history)
    if isinstance(history, dict):
        from .delivery import history_entries
        history = history_entries(history)
    floor = 6 if args.strict else 0
    result = select_result(
        candidates, history, args.limit, strict=args.strict,
        min_quality=floor if args.min_quality is None else args.min_quality,
        min_relevance=floor if args.min_relevance is None else args.min_relevance,
        profile=args.canonicalization or ("conservative" if args.strict else "legacy"),
        as_of=args.as_of, window_days=args.window_days,
    )
    payload = result.to_json() + "\n"
    outputs = {args.output: payload if args.format == "json" else render_source_pack(result)}
    if args.decisions is not None:
        # Check before constructing a mapping, which would erase an exact duplicate.
        if args.decisions == args.output:
            raise ValueError("output and decisions paths must differ")
        outputs[args.decisions] = payload
    write_outputs(outputs, inputs=[args.candidates, args.history], overwrite=args.overwrite)
    print(args.output)


def _record_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record only receipt-confirmed delivered items into a NEW history file.")
    parser.add_argument("selection", type=Path, help="saved JSON selection result")
    parser.add_argument("history", type=Path, help="existing legacy list or history envelope")
    parser.add_argument("receipt", type=Path, help="explicit report ID, delivery timestamp, and used items")
    parser.add_argument("output", type=Path, help="new history file; must not alias any input")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _record(args: argparse.Namespace) -> None:
    from .delivery import record_delivery

    result = record_delivery(load_json(args.selection), load_json(args.history), load_json(args.receipt))
    write_outputs(
        {args.output: stable_json(result) + "\n"},
        inputs=[args.selection, args.history, args.receipt], overwrite=args.overwrite,
    )
    print(args.output)


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    recording = bool(values and values[0] == "record-delivery")
    parser = _record_parser() if recording else _build_parser()
    args = parser.parse_args(values[1:] if recording else values)
    try:
        (_record if recording else _build)(args)
    except (ValueError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
