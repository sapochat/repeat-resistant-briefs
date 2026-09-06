# Repeat-Resistant Briefs

A deterministic, offline source-pack builder for recurring reports and newsletters. It ranks caller-supplied candidates, explains every selection or exclusion, and suppresses direct identity repeats against delivered history unless an admissible follow-up is supplied.

**Selection is not delivery.** Scores, rendered packs, and unused selections never advance history. Only a separate caller-confirmed delivery receipt does.

```text
caller collects sources and assigns scores
  → validated selection + decision audit → source pack
  → caller synthesizes, verifies, and delivers the report
  → receipt of actually used items → new delivered history → next selection
```

The runtime uses Python's standard library and requires Python 3.10+. It is not a collector, newsletter writer, model integration, semantic deduplicator, or evidence-verification service. Structured follow-ups establish event bookkeeping, not proof of truth or material importance. The 0.2.0 work is unreleased; the instructions below install this checkout, not a claimed public package release.

## Install from the checkout

Run these commands from the repository root in a POSIX shell:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

If your Python lacks `venv`/`ensurepip`, use an installed `uv` instead:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e .
```

Build tooling may require downloads during installation; selection itself is offline and has no third-party runtime dependencies.

## End-to-end local example

Generate Markdown and save the **same selection** as JSON for auditing and later receipt validation:

```bash
work=$(mktemp -d)
.venv/bin/repeat-resistant-briefs \
  examples/candidates.json examples/history.json "$work/source-pack.md" \
  --decisions "$work/selection.json"
```

This deliberately uses compatibility mode: the original sample contains a free-text follow-up, not a structured event. It selects `repo:openhuman`'s update and `paper:new-context`; the unqualified OpenHuman repeat is suppressed. The text justification is labeled **unverified**, not certified as a material change.

**Production boundary:** read the pack, synthesize the report, check evidence and editorial quality, deliver it through your own system, then make a receipt listing only what actually appeared. Do not record every selected item automatically. This package performs none of those publication steps.

The following commands are a **fixture simulation**, not a real delivery: `examples/delivery-receipt.json` explicitly acknowledges those two sample identities without event IDs. The old text-only follow-up has no structured event to acknowledge.

```bash
.venv/bin/repeat-resistant-briefs record-delivery \
  "$work/selection.json" examples/history.json \
  examples/delivery-receipt.json "$work/history-next.json"

.venv/bin/repeat-resistant-briefs \
  examples/candidates.json "$work/history-next.json" "$work/next-pack.md" \
  --decisions "$work/next-selection.json"
```

`history-next.json` is a new v1 envelope with `entries` and `receipts`; the original history is unchanged. Compatibility free text may admit the same update again on the next run: it has no event replay protection. Use strict structured events for that protection. An empty receipt (`items: []`) is also recorded, with no delivered entries, so the report ID still cannot be reused contradictorily.

For JSON-only selection, use `--format json` with a separate output filename. `--decisions` always contains the complete result, not just exclusions.

## Strict mode and explicit windows

```bash
.venv/bin/repeat-resistant-briefs \
  examples/candidates.json examples/history.json "$work/strict-pack.md" \
  --strict --window-days 30 --as-of 2026-07-21 \
  --decisions "$work/strict-selection.json"
```

Strict mode requires finite numeric quality/relevance scores and defaults to floors of 6/10 and conservative URL normalization. Here the fresh paper remains eligible, but the legacy text-only OpenHuman follow-up cannot override delivered history. `--min-quality`, `--min-relevance`, `--limit`, and `--canonicalization conservative|legacy` are explicit overrides. A window has inclusive UTC endpoints and requires `--as-of`; no current date is inferred. Date-only values mean midnight UTC. Undated history remains active with a warning, and dated history after an explicit `as_of` is invalid.

The [three-run strict demo](examples/multi-run/README.md) includes complete structured follow-ups and explicit simulated delivery receipts:

```bash
demo=$(mktemp -d)
.venv/bin/python examples/multi-run/run.py --output "$demo"
```

Across July 20–22, Alpha's stale repeat is suppressed, selected-but-undelivered Gamma remains eligible, Beta's new correction event is admitted, and that exact event's later replay is suppressed. Each day has Markdown, selection JSON, and receipt JSON; final history and a summary make the delivered-only state changes inspectable. These are synthetic fixtures, not verified reporting or actual publication receipts.

## Python API

```python
from repeat_resistant_briefs import load_json, select_result, render_source_pack
from repeat_resistant_briefs.delivery import history_entries, record_delivery

history = load_json("examples/history.json")
result = select_result(
    load_json("examples/candidates.json"),
    history_entries(history),
    strict=True, min_quality=6, min_relevance=6,
    profile="conservative", as_of="2026-07-21", window_days=30,
)
pack = render_source_pack(result)
selection = result.to_dict()  # result.to_json() is stable JSON
```

After actual delivery, `record_delivery(selection, history, receipt)` returns a new history envelope. It performs no file writes, network calls, or authentication of the claimed delivery. `build_result` aliases `select_result`. Retained `select_candidates` and `build_source_pack` wrappers use compatibility defaults; `canonical_url(url)` also retains its legacy default, unlike strict/conservative `select_result`.

## Files, concurrency, and trust

- Existing outputs require explicit `--overwrite`; it replaces only named outputs. Use fresh temporary directories for examples and separate versioned history files for real runs.
- Outputs may never alias inputs or each other, including hard links; output symlinks and symlink ancestors are refused. Output parent directories must exist for the CLI.
- Writes are staged, individual replacements are atomic, and caught publication failures attempt rollback. This is **not** a crash-atomic multi-file transaction and does not coordinate concurrent writers.
- Maintain a separate history per publication and use a single writer. Receipts are structural acknowledgments, not cryptographic proof of delivery.
- Inspect identity-collision and provenance warnings. URL matching is direct ID-or-URL matching, not transitive merging or semantic equivalence.
- Source text is untrusted. Markdown escaping/fencing protects structure, not downstream models against every prompt injection. Caller-owned synthesis and QA remain necessary.

## Contracts and development

- [Input, history, selection, and receipt schemas](docs/input-format.md)
- [Decision policy, reason codes, URL profiles, and migration notes](docs/decision-policy.md)
- [Portable caller workflow](SKILL.md)
- [Changelog](CHANGELOG.md)

Run tests and verify built artifacts separately:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip install build
build_dir=$(mktemp -d)
.venv/bin/python -m build --outdir "$build_dir"
.venv/bin/python scripts/verify_distribution.py "$build_dir"
```

The verifier expects one wheel and one source distribution already built. It installs the wheel outside the checkout, runs tests from the unpacked source distribution, checks CLI parity, and compares generated demo artifacts with packaged fixtures. CI targets Python 3.10, 3.12, and 3.14; a configured target is not a claim that remote CI has passed.

MIT licensed.
