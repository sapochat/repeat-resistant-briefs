# Input and artifact formats

All files are UTF-8 JSON. Use `load_json(path)` or `loads_json(text)` at the Python boundary: they reject duplicate object keys, nonfinite numbers (`NaN`, infinities, and overflow such as `1e999`), and malformed JSON. Inputs must be finite JSON data with UTF-8-encodable strings; lone Unicode surrogates are rejected, including inside extra metadata. Booleans are not numeric scores or integer settings. Unknown candidate/history metadata is retained, not interpreted as editorial evidence. Invalid input fails the run rather than silently dropping rows.

## Candidates

The root is a list of objects, including an empty list. Example strict candidate:

```json
[
  {
    "id": "benchmark:beta",
    "title": "Beta benchmark correction",
    "url": "https://example.org/beta",
    "quality": 9,
    "relevance": 8,
    "source": "research",
    "substance": "The publisher reports an evaluation correction.",
    "follow_up": {
      "event_id": "beta:correction-1",
      "what_changed": "The publisher corrected the evaluation split.",
      "why_it_matters": "The corrected comparison may change the prior assessment.",
      "evidence_url": "https://example.org/beta/correction-1"
    }
  }
]
```

| Field | Contract |
| --- | --- |
| `title`, `url` | Required nonblank strings. URL must pass the HTTP(S) validator described in [decision policy](decision-policy.md). |
| `id` | Optional nonblank string. Use a stable, publication-owned identifier. Numbers, null, and blank strings are invalid; IDs are not trimmed or coerced. |
| `quality`, `relevance` | Required in strict mode; finite JSON numbers in `[0, 10]`. Missing values default to zero with `missing_score_defaulted` diagnostics in compatibility mode. Supplied invalid values fail in either mode. |
| `source`, `substance` | Optional strings; empty strings allowed, null/numbers invalid. No source quotas or semantic analysis are applied. |
| `follow_up` | Optional object. When present, all four example fields are required nonblank strings; `evidence_url` must be a valid HTTP(S) URL. Validated even for fresh candidates and in compatibility mode. |
| `follow_up_reason` | Optional string, empty allowed. Only a nonblank reason can admit a repeat in compatibility mode; it is explicitly unverified. Strict mode does not use it to admit repeats. |
| `event_id` | Optional nonblank string, but a bare candidate event ID does not establish a structured follow-up or delivery event. Put the event in `follow_up.event_id`. |

Computed fields such as `canonical_url`, `identity`, `row_id`, `repeat`, and `score` are output metadata, not caller overrides. Supply raw URLs. The selector recomputes its own canonical URL and ranking fields.

Strict CLI defaults: required scores, quality/relevance floors of 6, conservative URL policy. Positional CLI without `--strict`: missing scores default to zero, floors of zero, legacy URL policy, free-text follow-ups accepted as unverified. `--min-quality`, `--min-relevance`, and `--canonicalization` override their respective defaults. `--limit` and `--window-days` are nonnegative integers; a window requires explicit `--as-of`. Zero limit is valid and selects nothing.

## Delivered history

Legacy input is a list of objects:

```json
[
  {
    "id": "benchmark:beta",
    "url": "https://example.org/beta",
    "delivered_at": "2026-07-20T12:00:00Z",
    "event_id": "beta:initial"
  }
]
```

Each entry requires a valid nonblank `url`; `id` and `event_id` are optional nonblank strings. Candidate title and scores are not required. Optional `follow_up`, when supplied, has the candidate structure; its event must agree with a supplied top-level `event_id`. Optional `follow_up_reason` must be a string.

`delivered_at` or legacy `date` may be omitted. Accepted JSON dates are `YYYY-MM-DD` (midnight UTC) or timezone-aware timestamps with seconds, for example `2026-07-20T12:00:00Z` or `2026-07-20T05:00:00-07:00`; fractional seconds are allowed. Naive timestamps fail. If both date fields exist, they must resolve to the same instant. See the inclusive window and undated-history rules in [decision policy](decision-policy.md).

New `record-delivery` output is a versioned envelope with exactly these top-level keys:

```json
{"schema_version":1,"entries":[],"receipts":[]}
```

`schema_version` is integer `1`, not a boolean. Both arrays contain objects. `entries` are delivered-history rows. `receipts` hold resolved report confirmations, including empty confirmations. Preserve both arrays together; do not reconstruct an envelope from entries alone or prune receipt records without a separate migration policy.

Each generated entry contains `identity`, `url`, `canonical_url`, `canonicalization_profile`, `canonicalization_version`, `report_id`, and normalized UTC `delivered_at`; `id`, structured `follow_up`, and its matching `event_id` are included when applicable. Identity is the original `id` if present, otherwise the canonical URL.

Each stored receipt contains exactly `report_id`, `delivered_at`, `items`, `canonicalization_profile`, and `canonicalization_version`. Its resolved items carry the entry's identity/URL/provenance and optional ID/event/follow-up, but not report ID or delivery time. Entries for that report must agree with the stored items and timestamp. Report IDs must be unique. Every entry carrying `report_id` requires a matching stored receipt; orphan report-tagged entries fail. At the `history_entries`/`record_delivery` validation boundary, a legacy list containing `report_id` is rejected with a migration error: a list alone cannot establish receipt provenance. Supply an explicitly reconciled v1 envelope backed by actual acknowledgments; do not manufacture receipts or silently rewrite old records. The row-list selector itself is not a receipt-integrity validator. Provenance must be a matching pair (`legacy`, `legacy-v1`) or (`conservative`, `conservative-v1`); contradictory identities, canonical URLs, event IDs, profiles, or receipt/entry evidence fail delivery-history validation.

The CLI accepts lists and envelopes. The pure selector accepts history **rows**, not envelopes: use `from repeat_resistant_briefs.delivery import history_entries` to validate and extract a detached list from either history format. `record_delivery` accepts either format and always returns an envelope. Keep one canonicalization policy per publication history; recording against contradictory stored provenance fails rather than silently migrating it.

## Selection result (not a delivery record)

`--format json` writes the same artifact as the `--decisions` JSON sidecar. Its fields are:

- `schema_version`: integer `1`.
- `selected`: ranked normalized candidate objects with `canonical_url`, `identity`, content-hash/occurrence `row_id`, `repeat`, and weighted `score`.
- `decisions`: one object per input occurrence, ordered by `row_id`. Fields: `row_id`, normalized `candidate`, `identity`, `canonical_url`, `disposition`, `code`, `explanation`, `duplicate_of` (representative row ID or null), `matched_history`, `score`, `score_components`, and `canonicalization_version`. Score components include `quality`, `relevance`, `weighted_quality`, and `weighted_relevance`.
- `policy`: `strict`, `min_quality`, `min_relevance`, `limit`, `canonicalization_profile`, `canonicalization_version`, `weights` (`quality: 0.55`, `relevance: 0.45`), `window_days`, UTC `as_of` (or null), `identity_matching: "direct_id_or_url"`, and `deduplication: "eligible_representatives_only"`.
- `diagnostics`: objects with stable `code`, explanatory text, and code-specific identity/alias/provenance fields.

Keep the generated selection artifact unchanged for delivery recording. Structural validation checks supported v1 policy, selected identities, URLs, and receipt references; it is not cryptographic authentication or proof that a report was sent. A scored or selected candidate has **not** thereby been delivered.

## Caller-supplied delivery receipt

The receipt has exactly `report_id`, `delivered_at`, and `items`:

```json
{
  "report_id": "daily-2026-07-21",
  "delivered_at": "2026-07-21T12:00:00Z",
  "items": [
    {"identity": "benchmark:beta", "event_id": "beta:correction-1"}
  ]
}
```

- `report_id` is a nonblank string unique within this publication history.
- `delivered_at` is a date/time string in the history format and must not precede the selection's explicit `as_of`. No wall-clock time is inferred or checked.
- `items` is a list of objects with required nonblank `identity`, optional `identity_type`, and optional nonblank `event_id` only. Match the exact selected `identity` string: no trimming, URL normalization, or ID/URL alias lookup is applied to receipt identities.
- `identity_type`, when supplied, must be exactly `"id"` or `"url"`. It refers to how the selected identity was derived: `"id"` for a row with an original `id`, `"url"` for a row without one (canonical-URL identity). Omit it when the identity text uniquely identifies a selected row. If an explicit ID equals another selected row's canonical-URL identity, both remain valid distinct entities; an untyped acknowledgment fails with `supply identity_type`. To acknowledge both, use two items with the same exact identity string and different identity types. Unknown/malformed types and types with no matching selected identity fail.
- Each resolved entity may appear only once per receipt, including when one acknowledgment is typed and another untyped. The disambiguator is not persisted: resolved receipt items and history entries already preserve original `id` presence, which determines their typed identity. Existing unambiguous receipts and output formats are unchanged.
- If the selected row has a structured follow-up, its exact `event_id` is required. Otherwise omit `event_id`; an arbitrary or bare candidate event cannot be acknowledged as structured evidence.
- Include **only actually delivered items**, even when the source pack selected more. `items: []` is valid even if selected identity text collides: it appends no entries but stores a receipt so report-ID reuse remains idempotent.

Replaying an identical resolved receipt returns unchanged history. Timestamp offsets are normalized and item order is ignored. Reusing the report ID with different delivery time, identities, URLs, provenance, or event evidence fails; changing editorial scores alone does not change the resolved receipt. The returned history is a new object, and the CLI writes it to a separate file without modifying any input.
