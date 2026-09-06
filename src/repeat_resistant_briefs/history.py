"""Explicit UTC history normalization and inclusive windows; no wall clock reads."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from .validation import nonnegative_int, stable_json, validate_rows

UTC = timezone.utc


def parse_timestamp(value: str | date | datetime, field: str = 'timestamp') -> datetime:
    if isinstance(value, datetime):
        stamp = value
    elif isinstance(value, date):
        stamp = datetime.combine(value, time(), UTC)
    elif isinstance(value, str):
        if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            stamp = datetime.combine(date.fromisoformat(value), time(), UTC)
        elif re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})', value):
            if not value.endswith('Z') and (int(value[-5:-3]) >= 24 or int(value[-2:]) >= 60):
                raise ValueError(f'{field} has an invalid timezone offset')
            stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
        else:
            raise ValueError(f'{field} must be an ISO date or timezone-aware timestamp')
    else:
        raise ValueError(f'{field} must be an ISO date or timezone-aware timestamp')
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError(f'{field} timestamp requires a timezone')
    try:
        return stamp.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError(f'{field} is outside supported UTC date range') from exc


def normalize_history(history: list[dict], *, profile: str = 'conservative', as_of=None, window_days: int | None = None) -> tuple[list[dict], list[dict]]:
    """Return active copied rows and diagnostics. Accept delivered_at or legacy date."""
    if window_days is not None:
        nonnegative_int(window_days, 'window_days')
        if as_of is None:
            raise ValueError('window_days requires explicit as_of')
    end = parse_timestamp(as_of, 'as_of') if as_of is not None else None
    try:
        start = end - timedelta(days=window_days) if window_days is not None and end is not None else None
    except OverflowError as exc:
        raise ValueError('window_days is outside supported date range') from exc
    rows, diagnostics = validate_rows(history, kind='history', profile=profile)
    active = []
    for index, row in enumerate(rows):
        try:
            stored_version = row.get('canonicalization_version')
            stored_profile = row.get('canonicalization_profile')
            if (stored_version is not None and stored_version != profile + '-v1') or (stored_profile is not None and stored_profile != profile):
                diagnostics.append({'code':'canonicalization_mismatch',
                                    'identity':row.get('id') or row['canonical_url'],
                                    'stored_version':stored_version,'stored_profile':stored_profile,
                                    'current_version':profile+'-v1',
                                    'explanation':'History was produced under a different URL policy; raw IDs are retained and URLs use the requested profile.'})
            if 'follow_up' in row:
                event_id = row['follow_up']['event_id']
                if 'event_id' in row and row['event_id'] != event_id:
                    raise ValueError('conflicting history event IDs')
                row['event_id'] = event_id
            stamps = [parse_timestamp(row[key], key) for key in ('delivered_at','date') if key in row]
            if stamps and any(s != stamps[0] for s in stamps):
                raise ValueError('conflicting delivered_at and date')
            if stamps:
                stamp = stamps[0]
                if end is not None and stamp > end:
                    raise ValueError('history delivery is after as_of')
                row['delivered_at'] = stamp.isoformat().replace('+00:00','Z')
                if start is not None and stamp < start:
                    continue
            else:
                diagnostics.append({'code':'undated_history_active','identity':row.get('id') or row['canonical_url'],'explanation':'Undated history remains active conservatively.'})
            active.append(row)
        except ValueError as exc:
            raise ValueError(f'history[{index}]: {exc}') from exc
    return sorted(active, key=stable_json), sorted(diagnostics, key=stable_json)


def window_history(history: list[dict], *, as_of, window_days: int, profile: str = 'conservative') -> tuple[list[dict], list[dict]]:
    return normalize_history(history, as_of=as_of, window_days=window_days, profile=profile)
