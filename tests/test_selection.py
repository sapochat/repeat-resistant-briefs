import copy
import itertools
import unittest
from repeat_resistant_briefs import briefs


def row(name='a', **extra):
    return dict(title=name, url='https://example.com/'+name, quality=9, relevance=9, **extra)


class SelectionTests(unittest.TestCase):
    def select(self, candidates, history=None, **kwargs):
        self.assertTrue(hasattr(briefs, 'select_result'), 'structured selection API missing')
        return briefs.select_result(candidates, history or [], **kwargs)

    def test_result_schema_version_and_dictionary_isolation(self):
        result=self.select([row()])
        document=result.to_dict()
        self.assertEqual(document.get('schema_version'),1)
        document['selected'][0]['title']='changed'
        self.assertEqual(result.selected[0]['title'],'a')

    def test_dispositions_and_floors(self):
        a=row(); weak=row('weak'); weak['quality']=5
        result=self.select([a, dict(a), weak, row('b'), row('old')], [{'url':row('old')['url']}], limit=1)
        self.assertCountEqual([d['disposition'] for d in result.decisions], ['selected','duplicate','below_floor','over_limit','recent_repeat'])
        for d in result.decisions:
            self.assertTrue(d['code']); self.assertTrue(d['explanation'])
            self.assertIn('score_components',d)
        duplicate=next(d for d in result.decisions if d['disposition']=='duplicate')
        self.assertTrue(duplicate['duplicate_of'])

    def test_permutations_are_byte_identical_without_mutation(self):
        rows=[row('a'),row('b'),row('a', id='a')]; before=copy.deepcopy(rows)
        outputs={self.select(list(p)).to_json() for p in itertools.permutations(rows)}
        self.assertEqual(len(outputs),1); self.assertEqual(rows,before)

    def test_eligible_update_not_shadowed(self):
        old=row(id='x'); update=row(id='x', follow_up={'event_id':'v2','what_changed':'release','why_it_matters':'fix','evidence_url':'https://e/proof'})
        update['quality']=8
        result=self.select([old,update],[{'id':'x','url':old['url']}])
        self.assertEqual(len(result.selected),1)
        self.assertEqual(result.selected[0]['follow_up']['event_id'],'v2')

    def test_changed_id_cannot_bypass_history(self):
        result=self.select([row(id='new')],[{'id':'old','url':row()['url']}])
        self.assertFalse(result.selected)
        self.assertTrue(result.decisions[0]['matched_history'])

    def test_bridge_is_diagnosed_not_transitively_merged(self):
        result=self.select([row('a',id='x'),row('b',id='x'),row('b',id='y')])
        self.assertTrue(any(d['code']=='ambiguous_identity_bridge' for d in result.diagnostics))
        self.assertEqual(len(result.decisions),3)

    def test_fresh_tie_and_score(self):
        update=row('a',follow_up={'event_id':'e','what_changed':'x','why_it_matters':'y','evidence_url':'https://e/x'})
        result=self.select([update,row('z')],[{'url':update['url']}],limit=1)
        self.assertEqual(result.selected[0]['title'],'z')
        self.assertEqual(result.selected[0]['score'],9)

    def test_representative_only_dedup_does_not_create_cluster(self):
        a=row('a',id='x'); bridge=row('b',id='x'); c=row('b',id='y')
        a['quality']=10; bridge['quality']=9; c['quality']=8
        result=self.select([a,bridge,c])
        self.assertEqual([r['id'] for r in result.selected],['x','y'])
        bridge_decision=next(d for d in result.decisions if d['candidate']['title']=='b' and d['candidate']['id']=='x')
        self.assertEqual(bridge_decision['duplicate_of'],result.selected[0]['row_id'])

    def test_all_occurrences_including_identical_rows_have_unique_ids(self):
        a=row(); result=self.select([a,a,a],limit=0)
        self.assertEqual(len({d['row_id'] for d in result.decisions}),3)
        self.assertCountEqual([d['disposition'] for d in result.decisions],['over_limit','duplicate','duplicate'])

    def test_strict_requires_both_scores(self):
        for field in ['quality','relevance']:
            c=row(); del c[field]
            with self.assertRaises(ValueError): self.select([c])

    def test_explicit_id_survives_url_change_and_namespace_is_typed(self):
        self.assertFalse(self.select([row('new',id='x')],[{'url':'https://e/old','id':'x'}]).selected)
        self.assertTrue(self.select([row('new',id='https://e/old')],[{'url':'https://e/old'}]).selected)

    def test_history_and_candidate_permutations_are_stable(self):
        candidates=[row('a',id='x'),row('b',id='x'),row('b',id='y')]
        history=[{'id':'x','url':'https://example.com/a'}, {'id':'y','url':'https://example.com/b'}]
        outputs={self.select(list(c),list(h)).to_json() for c in itertools.permutations(candidates) for h in itertools.permutations(history)}
        self.assertEqual(len(outputs),1)

    def test_compatibility_missing_scores(self):
        result=self.select([{'title':'a','url':'https://e/a'}],strict=False,min_quality=0,min_relevance=0)
        self.assertEqual(result.selected[0]['score'],0)
        self.assertTrue(any(d['code']=='missing_score_defaulted' for d in result.diagnostics))
