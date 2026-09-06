# Changelog

## 0.2.0 — Unreleased

This section describes the local implementation, not a published package or completed public release.

### Added

- `SelectionResult`, `select_result`, and `build_result` provide a structured selection contract with policy provenance, matched history, score components, diagnostics, stable row IDs, and one disposition per candidate occurrence.
- Strict selection requires finite numeric quality/relevance scores, defaults to floors of 6/10, and supports structured follow-ups with event ID, changed facts, significance, and evidence URL. Replaying a delivered event against directly matched active history is suppressed; this is event bookkeeping, not semantic or factual verification.
- Conservative-v1 URL identity preserves `www`, trailing slashes, fragments, and remaining query order/encoding while removing only `utm_*`, `fbclid`, and `gclid` tracking fields. Identity collision/bridge diagnostics expose conflicting aliases without transitive merging.
- Explicit UTC history normalization and inclusive `window_days`/`as_of` windows, undated-history warnings, future-history rejection relative to explicit `as_of`, and canonicalization-provenance diagnostics.
- CLI strict mode, score-floor and URL-policy overrides, explicit windows, JSON output, complete `--decisions` sidecars, and `--overwrite` opt-in.
- Pure `record_delivery` and `history_entries` APIs in `repeat_resistant_briefs.delivery`, plus the `record-delivery` CLI command. Only receipt-acknowledged selected identities/events enter history; versioned entries/receipts envelopes retain report idempotency even for empty deliveries.
- Strict three-day fixtures distinguish selected from delivered, keep an unused candidate eligible, admit a new correction event, and suppress its replay. Daily selection/receipt artifacts and final history accompany the Markdown packs and summary.
- Input/receipt schemas, reason-code and migration documentation, caller-owned editorial/delivery workflow, and an isolated distribution verifier for wheel execution, unpacked-source tests, CLI parity, and demo artifacts. CI configuration targets Python 3.10, 3.12, and 3.14.

### Changed

- Eligibility is established before representative-only deduplication. Rejected rows cannot suppress eligible rows, losing duplicates do not propagate aliases, and ties/accounting are deterministic. Both score floors must pass; no quota-driven padding is introduced.
- JSON loading rejects duplicate keys, nonfinite data, and strings that cannot be encoded as UTF-8. Candidate/history and configuration boundaries reject malformed types, scores, dates, follow-ups, and URLs instead of coercing invalid data or silently dropping rows. URL validation rejects unsafe schemes, credentials, malformed hosts/IPs/ports, controls, and backslashes in both modes.
- Markdown renders one already-computed selection, escapes structural data, fences untrusted source text, and exposes exclusions and warnings. It does not claim prompt-injection immunity or verify source claims.
- Output publication preflights aliases/symlinks/conflicts, stages writes, and attempts rollback on caught failures. Existing outputs require explicit overwrite; inputs remain protected. This is not a crash-atomic multi-file transaction or multi-writer protocol.
- Delivery validation rejects contradictory identities, URL/provenance, event evidence, report reuse, and receipt/history inconsistencies. It never authenticates actual delivery or automatically migrates old provenance.

### Compatibility and migration

- Retained positional CLI, `select_candidates`, and `build_source_pack` use legacy normalization, zero floors, missing-score defaults, and explicitly unverified free-text follow-ups. They still receive tightened type/URL validation.
- `canonical_url(url)` retains its legacy default; new `select_result`/`build_result` default to strict/conservative. Legacy and conservative normalization are intentionally different and must not be mixed silently.
- Ordinary legacy history lists remain accepted; new recording writes the v1 entries/receipts envelope to a separate history file. Report-tagged entries require matching receipt evidence rather than inferred provenance. See [migration details](docs/decision-policy.md#migration-from-01-style-calls) before changing existing datasets or consumers.

## 0.1.0

Initial source-pack builder with weighted candidate ranking, legacy URL normalization, delivered-history repeat checks, free-text follow-up justifications, compatibility Python helpers, a positional CLI, and example fixtures.
