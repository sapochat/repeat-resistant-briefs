"""Deterministic, auditable selection with explicit compatibility wrappers."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib

from .identity import canonical_url, identity, matches
from .history import normalize_history, parse_timestamp
from .validation import nonnegative_int, score, stable_json, validate_rows


@dataclass(frozen=True)
class SelectionResult:
    selected: list[dict]
    decisions: list[dict]
    policy: dict
    diagnostics: list[dict]

    def to_dict(self) -> dict:
        return deepcopy({'schema_version':1, 'selected':self.selected, 'decisions':self.decisions,
                         'policy':self.policy, 'diagnostics':self.diagnostics})

    def to_json(self) -> str:
        return stable_json(self.to_dict())


def _identity_diagnostics(rows: list[dict]) -> list[dict]:
    """Report collisions and open wedges, without creating alias clusters."""
    diagnostics = []
    ids, urls = {}, {}
    for row in rows:
        if 'id' in row:
            ids.setdefault(row['id'], set()).add(row['canonical_url'])
            urls.setdefault(row['canonical_url'], set()).add(row['id'])
    for kind, mapping in (('id', ids), ('url', urls)):
        for key, values in sorted(mapping.items()):
            if len(values) > 1:
                diagnostics.append({'code':'identity_collision','kind':kind,'identity':key,
                                    'aliases':sorted(values),'explanation':'One identity key has multiple aliases; only direct matches are used.'})
    for row in rows:
        if len(ids.get(row.get('id'), ())) > 1 and len(urls.get(row['canonical_url'], ())) > 1:
            diagnostics.append({'code':'ambiguous_identity_bridge','identity':row.get('id'),
                                'canonical_url':row['canonical_url'],
                                'explanation':'This row bridges conflicting ID and URL aliases; transitive merging is disabled.'})
    return [v for _,v in sorted({stable_json(d):d for d in diagnostics}.items())]


def select_result(candidates: list[dict], history: list[dict], limit: int = 8, *,
                  strict: bool = True, min_quality: float = 6, min_relevance: float = 6,
                  profile: str = 'conservative', as_of=None,
                  window_days: int | None = None) -> SelectionResult:
    """Rank once; classify eligibility before representative-only deduplication.

    Each input occurrence gets a stable content-hash/occurrence row_id and one
    disposition. Direct ID or URL matches suppress history repeats. Duplicate
    aliases are not propagated from losing rows, avoiding silent transitive unions.
    """
    nonnegative_int(limit, 'limit')
    if not isinstance(strict, bool):
        raise ValueError('strict must be a boolean')
    if profile not in ('legacy','conservative'):
        raise ValueError('unknown canonicalization profile')
    min_quality, min_relevance = score(min_quality,'min_quality'), score(min_relevance,'min_relevance')
    rows, diagnostics = validate_rows(candidates, strict=strict, profile=profile)
    active, history_diagnostics = normalize_history(history, profile=profile, as_of=as_of, window_days=window_days)
    diagnostics.extend(history_diagnostics)
    diagnostics.extend(_identity_diagnostics(rows + active))
    policy = {'strict':strict,'min_quality':min_quality,'min_relevance':min_relevance,
              'limit':limit,'canonicalization_profile':profile,'canonicalization_version':profile+'-v1',
              'weights':{'quality':0.55,'relevance':0.45},'window_days':window_days,
              'as_of':parse_timestamp(as_of,'as_of').isoformat().replace('+00:00','Z') if as_of is not None else None,
              'identity_matching':'direct_id_or_url','deduplication':'eligible_representatives_only'}
    occurrences = Counter()
    prepared = []
    for row in sorted(rows, key=stable_json):
        content = stable_json(row)
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        occurrences[digest] += 1
        row['row_id'] = f'{digest}:{occurrences[digest]}'
        row['identity'] = row.get('id') or row['canonical_url']
        prior = [deepcopy(h) for h in active if matches(row,h)]
        row['repeat'] = bool(prior)
        row['score'] = row['quality'] * 0.55 + row['relevance'] * 0.45
        follow = row.get('follow_up')
        code, disposition, explanation = 'fresh_candidate', None, 'Fresh candidate meets editorial floors.'
        if prior:
            if follow and any(h.get('event_id') == follow['event_id'] for h in prior):
                disposition, code, explanation = 'recent_repeat', 'event_already_delivered', 'This event was already delivered for a directly matched entity.'
            elif follow:
                code, explanation = 'structured_follow_up', 'A new structured event supports this follow-up.'
            elif not strict and row.get('follow_up_reason','').strip():
                code, explanation = 'unverified_follow_up', 'Compatibility follow-up: free-text reason is unverified.'
            else:
                disposition, code, explanation = 'recent_repeat', 'missing_follow_up', 'Recently delivered without a concrete follow-up.'
        if disposition is None and (row['quality'] < min_quality or row['relevance'] < min_relevance):
            disposition, code, explanation = 'below_floor', 'below_editorial_floor', 'Quality or relevance is below the configured editorial floor.'
        decision = {'row_id':row['row_id'],'candidate':deepcopy(row),'identity':row['identity'],
                    'canonical_url':row['canonical_url'],'disposition':disposition,'code':code,
                    'explanation':explanation,'duplicate_of':None,'matched_history':prior,
                    'score':row['score'],'score_components':{'quality':row['quality'],'relevance':row['relevance'],
                    'weighted_quality':row['quality']*0.55,'weighted_relevance':row['relevance']*0.45},
                    'canonicalization_version':policy['canonicalization_version']}
        prepared.append((row, decision))
    prepared.sort(key=lambda pair: (-pair[0]['score'],pair[0]['repeat'],pair[0]['identity'],pair[0]['canonical_url'],pair[0]['row_id']))
    selected, decisions, representatives = [], [], []
    for row, decision in prepared:
        if decision['disposition'] is None:
            duplicate = next((rep for rep in representatives if matches(row,rep)),None)
            if duplicate is not None:
                decision.update(disposition='duplicate',code='duplicate_candidate',
                                explanation='A higher-ranked eligible direct match is the representative.',duplicate_of=duplicate['row_id'])
            else:
                representatives.append(row)
                if len(selected) < limit:
                    decision['disposition'] = 'selected'
                    selected.append(row)
                else:
                    decision.update(disposition='over_limit',code='selection_limit',explanation='Eligible representative exceeds the selection limit.')
        decisions.append(decision)
    decisions.sort(key=lambda d:d['row_id'])
    diagnostics.sort(key=stable_json)
    return SelectionResult(selected, decisions, policy, diagnostics)


# New build API returns the same structured contract; rendering consumes it later.
build_result = select_result


def select_candidates(candidates: list[dict], history: list[dict], limit: int = 8) -> tuple[list[dict], list[dict]]:
    result = select_result(candidates, history, limit, strict=False, min_quality=0, min_relevance=0, profile='legacy')
    suppressed = []
    for decision in result.decisions:
        if decision['disposition'] == 'recent_repeat':
            row = deepcopy(decision['candidate'])
            row['suppression_reason'] = decision['explanation']
            suppressed.append(row)
    return result.selected, suppressed

def build_source_pack(candidates: list[dict], history: list[dict], limit: int = 8) -> str:
    result = select_result(candidates, history, limit, strict=False, min_quality=0, min_relevance=0, profile='legacy')
    return render_source_pack(result)


def render_source_pack(result: SelectionResult) -> str:
    from .rendering import render_source_pack as render
    return render(result)
