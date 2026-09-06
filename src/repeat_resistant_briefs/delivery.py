"""Pure delivered-only history updates; structural checks are not authentication.

Only caller-acknowledged items are recorded. No clock, file I/O, inferred usage,
or cryptographic provenance is involved. Legacy lists without report IDs are accepted;
new writes use a v1 envelope so even empty report confirmations are remembered.
"""
from __future__ import annotations

from copy import deepcopy
from .history import normalize_history, parse_timestamp
from .validation import nonblank, nonnegative_int, score, stable_json, validate_rows

_PROVENANCE = ('canonicalization_profile', 'canonicalization_version')
_ITEM_FIELDS = ('identity', 'id', 'url', 'canonical_url', *_PROVENANCE, 'event_id', 'follow_up')


def _identity_key(row):
    return ('id' if 'id' in row else 'url', row['identity'])


def _version(value, label):
    if type(value) is not int or value != 1:
        raise ValueError(f'{label} schema_version must be 1')


def _stamp(value, label):
    if not isinstance(value, str):
        raise ValueError(f'{label} must be an ISO date/time string')
    return parse_timestamp(value, label).isoformat().replace('+00:00', 'Z')


def _profile(obj, required=False):
    present = [key in obj for key in _PROVENANCE]
    if not any(present) and not required:
        return None
    profile = obj.get('canonicalization_profile')
    if not all(present) or profile not in ('conservative', 'legacy') or obj.get('canonicalization_version') != profile + '-v1':
        raise ValueError('conflicting or unsupported canonicalization profile/version')
    return profile


def _rows(rows, profile, selected=False):
    normalized, _ = validate_rows(rows, kind='candidates' if selected else 'history', profile=profile)
    identities = set()
    for raw, row in zip(rows, normalized):
        if 'schema_version' in raw:
            _version(raw['schema_version'], 'row')
        provenance = _profile(raw)
        if provenance is not None and provenance != profile:
            raise ValueError('conflicting canonicalization profiles')
        if 'canonical_url' in raw and raw['canonical_url'] != row['canonical_url']:
            raise ValueError('canonical_url conflicts with raw URL and profile')
        expected = row.get('id') or row['canonical_url']
        if ('identity' in raw or selected) and raw.get('identity') != expected:
            raise ValueError('identity conflicts with original ID or canonical URL')
        key = ('id' if 'id' in row else 'url', expected)
        if selected and key in identities:
            raise ValueError('duplicate selected identity')
        identities.add(key)
        if 'follow_up' in row and 'event_id' in row and row['event_id'] != row['follow_up']['event_id']:
            raise ValueError('conflicting event IDs')
    if not selected:
        normalize_history(normalized, profile=profile)  # Validate dates without a wall clock.
    return normalized


def _selection(selection):
    if not isinstance(selection, dict):
        raise ValueError('selection must be an object')
    stable_json(selection)
    _version(selection.get('schema_version'), 'selection')
    policy = selection.get('policy')
    if not isinstance(policy, dict):
        raise ValueError('selection policy must be an object')
    profile = _profile(policy, required=True)
    for field, expected in [('weights', {'quality': 0.55, 'relevance': 0.45}),
                            ('identity_matching', 'direct_id_or_url'),
                            ('deduplication', 'eligible_representatives_only')]:
        if policy.get(field) != expected:
            raise ValueError(f'unsupported v1 policy.{field}')
    if type(policy.get('strict')) is not bool:
        raise ValueError('policy.strict must be a boolean')
    nonnegative_int(policy.get('limit'), 'policy.limit')
    for field in ('min_quality', 'min_relevance'):
        score(policy.get(field), 'policy.' + field)
    if policy.get('window_days') is not None:
        nonnegative_int(policy['window_days'], 'policy.window_days')
        if policy.get('as_of') is None:
            raise ValueError('policy.window_days requires as_of')
    if policy.get('as_of') is not None:
        _stamp(policy['as_of'], 'policy.as_of')
    for field in ('decisions', 'diagnostics'):
        if not isinstance(selection.get(field), list) or any(not isinstance(row, dict) for row in selection[field]):
            raise ValueError(f'selection.{field} must be a list of objects')
    rows = _rows(selection.get('selected'), profile, selected=True)
    if len(rows) > policy['limit']:
        raise ValueError('selected count exceeds policy.limit')
    return policy, {_identity_key(row): row for row in rows}


def _receipt(receipt, resolved=False):
    fields = {'report_id', 'delivered_at', 'items'}
    if resolved:
        fields.update(_PROVENANCE)
    if not isinstance(receipt, dict) or set(receipt) != fields:
        raise ValueError('receipt fields must be report_id, delivered_at, items' + (' and provenance' if resolved else ''))
    nonblank(receipt['report_id'], 'report_id')
    stamp = _stamp(receipt['delivered_at'], 'delivered_at')
    if not isinstance(receipt['items'], list):
        raise ValueError('receipt.items must be a list')
    identities = set()
    for item in receipt['items']:
        if not isinstance(item, dict) or (not resolved and (set(item) - {'identity', 'identity_type', 'event_id'})):
            raise ValueError('receipt items require identity and optional identity_type, event_id only')
        identity = nonblank(item.get('identity'), 'receipt identity')
        if not resolved and 'identity_type' in item and item['identity_type'] not in ('id', 'url'):
            raise ValueError("receipt identity_type must be 'id' or 'url'")
        key = _identity_key(item) if resolved else (item.get('identity_type'), identity)
        if key in identities:
            raise ValueError('duplicate receipt identity')
        identities.add(key)
        if 'event_id' in item:
            nonblank(item['event_id'], 'event_id')
    return stamp


def _history(history, profile=None):
    stable_json(history)
    if isinstance(history, list):
        if any(isinstance(row, dict) and 'report_id' in row for row in history):
            raise ValueError('legacy history with report_id requires migration to a v1 envelope '
                             'with matching recorded receipts; a list cannot verify report reuse')
        envelope = {'schema_version': 1, 'entries': deepcopy(history), 'receipts': []}
    elif isinstance(history, dict) and set(history) == {'schema_version', 'entries', 'receipts'}:
        _version(history['schema_version'], 'history')
        envelope = deepcopy(history)
    else:
        raise ValueError('history must be a legacy list or v1 entries/receipts envelope')
    for key in ('entries', 'receipts'):
        if not isinstance(envelope[key], list) or any(not isinstance(row, dict) for row in envelope[key]):
            raise ValueError(f'history.{key} must be a list of objects')
    profiles = {_profile(row) for key in ('entries', 'receipts') for row in envelope[key]}
    profiles.discard(None)
    if profile is not None:
        profiles.add(profile)
    if len(profiles) > 1:
        raise ValueError('conflicting history and selection canonicalization profiles')
    profile = next(iter(profiles), 'conservative')
    _rows(envelope['entries'], profile)
    reports = set()
    for record in envelope['receipts']:
        _receipt(record, resolved=True)
        _profile(record, required=True)
        if record['report_id'] in reports:
            raise ValueError('duplicate history report_id')
        reports.add(record['report_id'])
        _rows(record['items'], profile)
        for item in record['items']:
            _profile(item, required=True)
            if set(item) - set(_ITEM_FIELDS) or not {'identity', 'url', 'canonical_url'}.issubset(item):
                raise ValueError('malformed resolved receipt item')
            if ('event_id' in item) != ('follow_up' in item):
                raise ValueError('resolved receipt event_id and follow_up must be present together')
            if 'follow_up' in item and item['event_id'] != item['follow_up']['event_id']:
                raise ValueError('resolved follow-up requires matching event_id')
        actual = []
        for entry in envelope['entries']:
            if entry.get('report_id') == record['report_id']:
                actual.append(dict(entry, delivered_at=_stamp(entry.get('delivered_at'), 'delivered_at')))
        expected = [dict(item, report_id=record['report_id'],
                         delivered_at=_stamp(record['delivered_at'], 'delivered_at')) for item in record['items']]
        if sorted(actual, key=stable_json) != sorted(expected, key=stable_json):
            raise ValueError('history entries contradict stored delivery receipt')
    for entry in envelope['entries']:
        if 'report_id' in entry:
            report_id = nonblank(entry['report_id'], 'history entry report_id')
            if report_id not in reports:
                raise ValueError('history entry report_id has no matching recorded receipt')
    return envelope


def history_entries(history: list | dict) -> list:
    """Validate either history format and return detached rows for the selector."""
    return _history(history)['entries']


def record_delivery(selection: dict, history: list | dict, receipt: dict) -> dict:
    """Return a new v1 history, or an unchanged copy for an identical receipt.

    Receipt identities are exact selected identities, not fuzzy URL/ID aliases.
    Optional identity_type ('id' or 'url') is required for colliding identity text.
    Report reuse compares normalized timestamps and resolved identity/URL/event
    evidence, not editorial scores. Delivery may be later than any wall clock,
    but must not precede the artifact's explicit policy.as_of.
    """
    policy, selected = _selection(selection)
    stamp = _receipt(receipt)
    if policy.get('as_of') is not None and parse_timestamp(stamp) < parse_timestamp(policy['as_of']):
        raise ValueError('delivered_at must not precede selection as_of')
    envelope = _history(history, policy['canonicalization_profile'])
    provenance = {key: policy[key] for key in _PROVENANCE}
    items = []
    acknowledged = set()
    for acknowledgment in receipt['items']:
        identity = acknowledgment['identity']
        kinds = (acknowledgment['identity_type'],) if 'identity_type' in acknowledgment else ('id', 'url')
        matches = [selected[(kind, identity)] for kind in kinds if (kind, identity) in selected]
        if not matches:
            raise ValueError('receipt identity was not selected: ' + acknowledgment['identity'])
        if len(matches) > 1:
            raise ValueError('ambiguous receipt identity; supply identity_type: ' + identity)
        row = matches[0]
        key = _identity_key(row)
        if key in acknowledged:
            raise ValueError('duplicate receipt identity')
        acknowledged.add(key)
        event = row.get('follow_up', {}).get('event_id')
        if event is not None and acknowledgment.get('event_id') != event:
            raise ValueError('follow-up receipt requires the selected event_id')
        if 'event_id' in acknowledgment and acknowledgment['event_id'] != event:
            raise ValueError('receipt event_id does not match selected structured event')
        item = {key: deepcopy(row[key]) for key in _ITEM_FIELDS if key in row}
        item.pop('event_id', None)  # A bare candidate event ID is not structured evidence.
        item.update(provenance)
        if event is not None:
            item['event_id'] = event
        items.append(item)
    normalized = dict(report_id=receipt['report_id'], delivered_at=stamp,
                      items=sorted(items, key=stable_json), **provenance)
    for prior in envelope['receipts']:
        if prior['report_id'] == receipt['report_id']:
            comparable = dict(prior, delivered_at=_stamp(prior['delivered_at'], 'delivered_at'),
                              items=sorted(prior['items'], key=stable_json))
            if comparable != normalized:
                raise ValueError('report_id already has a contradictory delivery receipt')
            return envelope
    envelope['entries'].extend(dict(deepcopy(item), report_id=receipt['report_id'], delivered_at=stamp) for item in items)
    envelope['receipts'].append(normalized)
    return envelope
