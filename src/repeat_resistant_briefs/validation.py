"""Small shared boundary validators. All invalid input raises ValueError."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from .identity import canonical_url


def loads_json(text: str | bytes) -> object:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    def constant(value):
        raise ValueError(f'nonfinite JSON number: {value}')
    if isinstance(text, bytes):
        text = text.decode('utf-8')
    if not isinstance(text, str):
        raise ValueError('JSON input must be UTF-8 bytes or text')
    result = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    # Also reject overflow such as 1e999, which parse_constant does not see.
    stable_json(result)
    return result


def load_json(path: str | Path) -> object:
    return loads_json(Path(path).read_bytes())


def stable_json(value: object) -> str:
    try:
        serialized = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
        # ASCII escaping must not conceal strings that cannot be written as UTF-8.
        # Serialize first so invalid types and circular containers are rejected.
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                item.encode('utf-8')
            elif isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, (list, tuple)):
                pending.extend(item)
        return serialized
    except (TypeError, ValueError) as exc:
        raise ValueError(f'input must be finite JSON data: {exc}') from exc


def nonblank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a nonblank string')
    return value


def score(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10 or not math.isfinite(value):
        raise ValueError(f'{field} must be a finite number from 0 to 10')
    return float(value)


def nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'{field} must be a nonnegative integer')
    return value


def validate_rows(rows: object, *, kind: str = 'candidates', strict: bool = True, profile: str = 'conservative') -> tuple[list[dict], list[dict]]:
    if not isinstance(rows, list):
        raise ValueError(f'{kind} must be a JSON list')
    output, diagnostics = [], []
    for index, original in enumerate(rows):
        try:
            if not isinstance(original, dict):
                raise ValueError(f'{kind} rows must be JSON objects')
            row = copy.deepcopy(original)
            row['canonical_url'] = canonical_url(nonblank(row.get('url'), 'url'), profile)
            if 'id' in row:
                nonblank(row['id'], 'id')
            for field in ('event_id',):
                if field in row:
                    nonblank(row[field], field)
            if 'follow_up_reason' in row and not isinstance(row['follow_up_reason'], str):
                raise ValueError('follow_up_reason must be a string when present')
            if 'follow_up' in row:
                follow = row['follow_up']
                if not isinstance(follow, dict):
                    raise ValueError('follow_up must be an object')
                for field in ('event_id','what_changed','why_it_matters','evidence_url'):
                    nonblank(follow.get(field), 'follow_up.' + field)
                try:
                    canonical_url(follow['evidence_url'], profile)
                except ValueError as exc:
                    raise ValueError(f'follow_up.evidence_url: {exc}') from exc
            if kind == 'candidates':
                nonblank(row.get('title'), 'title')
                for field in ('source','substance'):
                    if field in row and not isinstance(row[field], str):
                        raise ValueError(f'{field} must be a string')
                for field in ('quality','relevance'):
                    if field not in row:
                        if strict:
                            raise ValueError(f'{field} is required in strict mode')
                        row[field] = 0
                        diagnostics.append({'code':'missing_score_defaulted','field':field,'identity':row.get('id') or row['canonical_url'],'explanation':f'Missing {field} defaults to zero in compatibility mode.'})
                    row[field] = score(row[field], field)
            stable_json(row)
            output.append(row)
        except ValueError as exc:
            raise ValueError(f'{kind}[{index}]: {exc}') from exc
    return output, diagnostics
