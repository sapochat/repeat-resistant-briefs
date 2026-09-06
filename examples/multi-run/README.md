# Three-run strict example

A synthetic, offline fixture sequence demonstrates that **selected is not delivered** and that structured events are recorded separately from entities. It does not send a report or verify the fixture's editorial claims.

Run from the repository root after the [local installation](../../README.md#install-from-the-checkout):

```bash
demo=$(mktemp -d)
.venv/bin/python examples/multi-run/run.py --output "$demo"
```

The runner reads `days.json`, uses strict selection with quality/relevance floors of 6, conservative URL normalization, and an explicit 30-day inclusive history window ending at each day's UTC midnight. Each day provides its own simulated receipt. Only that receipt—not the selected list—advances history.

| Day | Selected | Receipt-confirmed delivery | Why it matters |
| --- | --- | --- | --- |
| 2026-07-20 | Alpha, Beta, Gamma | Alpha, Beta | Gamma was considered but not used, so it must not enter delivered history. |
| 2026-07-21 | Beta, Delta, Gamma | Gamma, Beta, Delta | Gamma remains eligible. Stale Alpha is suppressed. Beta is a directly matched entity with a new structured correction event. |
| 2026-07-22 | Epsilon | Epsilon | Beta reuses the correction event already recorded on day 2 and is suppressed, even though it again supplies structured follow-up fields. |

The correction has caller-supplied `what_changed`, `why_it_matters`, and `evidence_url`. The selector checks their presence and event-ID novelty, not whether the correction is true or materially changes a conclusion.

## Artifacts

For each of these stems:

- `day-1-2026-07-20`
- `day-2-2026-07-21`
- `day-3-2026-07-22`

The runner writes `.md` (source pack), `.selection.json` (complete policy/decisions/diagnostics), and `.receipt.json` (the explicit simulated acknowledgment). It also writes:

- `history.json`: final v1 delivered-history envelope, including resolved receipt records.
- `summary.json`: selected, delivered, and recent-repeat-suppressed identities plus artifact filenames for each day. The suppressed list is not a general list of every exclusion; inspect selection JSON for full accounting.

Committed reference artifacts are in [`output/`](output/). To deliberately regenerate those files rather than use a fresh directory:

```bash
.venv/bin/python examples/multi-run/run.py --output examples/multi-run/output --overwrite
```

Existing named artifacts are refused unless `--overwrite` is supplied. Unrelated files are not removed. Inputs, symlink paths, and aliased output targets are protected by the shared file writer. All days are computed before artifact publication; staged writes and rollback on caught failures are not a crash-atomic transaction or concurrent-writer coordination.

In production, replace these fixture acknowledgments with caller-confirmed receipts **after** synthesis, QA, and actual delivery. Keep a separate history per publication and a single writer. See [receipt format and idempotency](../../docs/input-format.md#caller-supplied-delivery-receipt).
