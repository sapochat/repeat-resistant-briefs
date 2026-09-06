# Decision policy

This is a deterministic, offline selector over caller-supplied evidence and scores. It neither verifies sources nor proves that a follow-up is true or materially important. No network access, model call, fuzzy/semantic deduplication, source diversity quota, or implicit current-time lookup is involved.

## URL and entity identity

A direct match means **equal nonblank IDs OR equal canonical URLs**. IDs are compared as exact strings, independently of URLs; an ID string that happens to look like another row's URL is not an ID-to-URL match. Different URLs with the same ID, and different IDs with the same URL, therefore match directly.

Delivery acknowledgments use a narrower rule than repeat matching: exact selected `identity` text plus its type (original `id` presence, otherwise canonical URL), never an alias. Optional receipt `identity_type: "id" | "url"` disambiguates equal text from different identity types without rewriting identifiers or rejecting valid candidates. Untyped acknowledgments are accepted only when unique; ambiguity requires `supply identity_type`. Duplicate acknowledgments of the same resolved entity fail, even if one is typed and one untyped. Stored receipts infer the type from their existing optional `id`, so no extra output metadata is needed. Recording either or both entities preserves their separate identities for subsequent direct history matching. See [receipt format](input-format.md#caller-supplied-delivery-receipt).

Conflicting aliases produce `identity_collision` diagnostics. A row bridging conflicting ID and URL aliases may produce `ambiguous_identity_bridge`. No transitive alias cluster is built. For example, A `(id=x, url=u)`, B `(id=x, url=v)`, and C `(id=y, url=v)` do not make A and C identical just because B exists. A losing duplicate contributes no aliases to its representative. History matching likewise checks each active row directly, without following chains. Diagnostics describe conflicts; they do not resolve the caller's identity taxonomy.

### Versioned canonicalization

Both profiles:

- Accept HTTP and HTTPS only; schemeless host URLs and `//host/path` get HTTPS.
- Lowercase scheme/host, encode internationalized hosts with IDNA, normalize default ports (HTTP 80, HTTPS 443), and retain nondefault ports.
- Strip surrounding whitespace, but reject embedded control characters, backslashes, credentials, missing/malformed hosts, invalid IP literals, and invalid or empty ports. Nonblank string input is required. Arbitrary schemes such as `javascript:` and `file:` are rejected.
- Remove query pairs whose URL-decoded, case-insensitive key starts with `utm_`, or is exactly `fbclid` or `gclid`. This is the complete tracking rule: `ref`, `source`, `fbclid_extra`, and other unrecognized keys remain.
- Do not equate HTTP with HTTPS, follow redirects, or inspect destination content.

| Detail | `conservative-v1` | `legacy-v1` |
| --- | --- | --- |
| `www.` hostname prefix | Preserved | Removed |
| Path trailing slashes | Preserved, including empty path vs `/` | All trailing slashes removed; empty becomes `/` |
| Fragment | Preserved | Removed |
| Remaining query | Original pair order, duplicates, and encoding preserved | Parsed, sorted, and re-encoded; duplicate pairs retained |

These distinctions can change matches. `https://www.example.org/a/#part` and `https://example.org/a` remain different conservatively but match under legacy normalization. Canonicalization is identity bookkeeping, not a security endorsement of a URL.

`canonical_url(url)` retains its **legacy default** for compatibility. `select_result(...)` and its `build_result` alias default to **strict/conservative**. Pass `profile=` explicitly when mixing APIs. The CLI chooses conservative with `--strict`, legacy otherwise, unless `--canonicalization` overrides it.

## Delivered-history window

Only supplied delivered history suppresses repeats. Candidate files, rankings, rendered packs, and unused selections are not history updates.

- Without a window, all supplied history is active, subject to validation.
- `window_days` requires explicit `as_of`; there is no clock default.
- Normalize dates/timestamps to UTC. A date-only `as_of` is midnight UTC, not the end of that calendar day.
- With a window, include both endpoints: `as_of - window_days <= delivered_at <= as_of`. A zero-day window admits only that instant, plus undated rows.
- A dated history row later than an explicit `as_of` is an error, even when no window is supplied. Without `as_of`, there is no future-time check.
- Undated rows remain active conservatively and produce `undated_history_active`; they do not silently expire.
- Legacy `date` is accepted; if both it and `delivered_at` exist, they must denote the same instant.
- Selection re-canonicalizes raw history URLs under the requested profile. Stored profile/version differences produce `canonicalization_mismatch`. Delivery recording is stricter: contradictory stored provenance is rejected, not migrated automatically.

Keep full delivered history and apply windows on read. Receipt records enforce report idempotency independently of which entries are currently inside the selection window.

## Eligibility, event novelty, and ranking

1. Validate all candidates/history and compute canonical identities. Invalid rows fail the run; they are not silently omitted.
2. For each candidate, gather all direct matches in active history.
3. If a structured follow-up's `event_id` already appears in those matches, classify `recent_repeat` / `event_already_delivered`. Changing its wording does not make the event new.
4. A directly matched entity with a new structured event is eligible with `structured_follow_up`. Strict mode requires the four nonblank follow-up fields; a free-text reason alone does not suffice. Compatibility mode can instead use a nonblank `follow_up_reason`, classified `unverified_follow_up`. Otherwise the repeat is `recent_repeat` / `missing_follow_up`.
5. Eligible candidates must meet **both** inclusive score floors. A high quality score cannot compensate for relevance below its floor. Failure is `below_floor` / `below_editorial_floor`.
6. Rank by descending `0.55 * quality + 0.45 * relevance`; exact score ties prefer fresh over repeat, then lexicographically smaller identity, canonical URL, and stable row ID.
7. Deduplicate eligible rows against higher-ranked eligible **representatives only**. A direct match is `duplicate` / `duplicate_candidate` with `duplicate_of`. Rejected repeats and below-floor rows cannot block eligible rows. A losing duplicate cannot propagate an alias.
8. Select representatives up to `limit`. Further representatives are `over_limit` / `selection_limit`; they still represent their direct duplicates. No padding or quotas are applied, so an empty selection is valid.

Structured evidence establishes a schema-complete, not-previously-recorded event **within directly matched active history**. It does not verify the evidence URL, semantic novelty, truth, magnitude, or changed implication. A new event ID can be misleading; caller-owned editorial QA must catch that. Conversely, an event outside the active window no longer supplies an in-window replay veto. Receipts record the exact event that was delivered, not a model's interpretation of it.

## Audit contract

Every input occurrence gets exactly one disposition: `selected`, `recent_repeat`, `below_floor`, `duplicate`, or `over_limit`. Their counts sum to input length, even for byte-equivalent repeated rows. Normalized content hashes plus occurrence suffixes distinguish such rows. Inputs are copied, not mutated; stable sorting and serialization make the same data/policy deterministic under input permutation.

| Reason code | Meaning |
| --- | --- |
| `fresh_candidate` | No direct active-history match; floors passed. |
| `structured_follow_up` | Direct repeat has a structured event absent from matched active history; floors passed. |
| `unverified_follow_up` | Compatibility-only repeat admitted by nonblank free text; floors passed. |
| `event_already_delivered` | Structured event already appears in direct active-history matches. |
| `missing_follow_up` | Repeat lacks an admissible follow-up. |
| `below_editorial_floor` | Quality or relevance fails its configured floor. |
| `duplicate_candidate` | Higher-ranked eligible direct representative exists. |
| `selection_limit` | Eligible representative exceeds limit. |

The first three codes describe selected eligibility; later deduplication/limit decisions replace them for excluded rows. Repeat vetoes are evaluated before floors, so a row can be low-scoring but receive a repeat code. Diagnostics are separate from dispositions: `missing_score_defaulted`, `undated_history_active`, `canonicalization_mismatch`, `identity_collision`, and `ambiguous_identity_bridge` do not create extra candidate decisions.

JSON is the complete audit artifact. Markdown renders the same computed result, including selected material, exclusion reasons, history warnings, and policy. Escaping and fenced untrusted source text protect Markdown structure; they do not guarantee resistance to prompt injection. Downstream writers must treat source text as data, not instructions.

Rendered matched-history dates are associated with each selected candidate's stable `row_id`, not its potentially shared identity text.

## Migration from 0.1-style calls

- Positional CLI invocation, `select_candidates(candidates, history, limit=8)`, and `build_source_pack(candidates, history, limit=8)` remain compatibility paths: legacy URL policy, no positive floors, optional scores defaulting to zero, and explicitly unverified free-text follow-ups. `select_candidates` still returns `(selected, suppressed)`; `suppressed` includes only recent-repeat exclusions, not the full accounting. Use `select_result` for all decisions.
- Compatibility is not permissive parsing. Both modes now reject wrong root/row types; missing or blank candidate title/URL; nonstring/blank IDs; wrong optional string types; malformed follow-up objects or evidence URLs; boolean, string, nonfinite, out-of-range scores; and invalid settings. Strict mode additionally rejects missing scores. JSON helpers reject duplicate keys, nonfinite values, and non-UTF-8-encodable strings (including lone Unicode surrogates in extra metadata) rather than accepting ambiguous or unwritable data.
- URL input no longer tolerates arbitrary schemes, credentials, malformed hosts/IPs/ports, controls, backslashes, or nonstring/blank values. Validate old datasets before switching policy. Tracking removal is only `utm_*`, `fbclid`, and `gclid`; do not assume arbitrary referral fields disappear.
- Dates must be explicit valid dates or timezone-aware timestamps. Conflicting date/event evidence fails. Undated legacy history remains active with a warning; a future row relative to explicit `as_of` fails.
- `canonical_url` defaults to legacy while `select_result` defaults to conservative; moving from wrappers can therefore change identity matches as well as score/follow-up eligibility. Reconcile IDs and provenance deliberately; do not simply relabel stored canonical URLs.
- Save selection JSON and record actual delivery separately. New history writes use the v1 entries/receipts envelope; use `history_entries` when passing that history to the row-list Python selector. Report-tagged envelope entries require matching stored receipts. Delivery/history-envelope validation rejects legacy lists carrying `report_id` with a migration error; it cannot reconstruct or assume receipt provenance. Reconcile old records against actual delivery evidence explicitly—no automatic rewriting or invented receipts. Do not advance history from `selected` alone.
- Existing output files now require `--overwrite`. Outputs must never alias inputs or each other, and symlink output paths are refused. Use new history filenames even with overwrite enabled. File staging and rollback on caught failures are not a crash-atomic multi-file transaction or a concurrency protocol.
