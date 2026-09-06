import unittest
from repeat_resistant_briefs import briefs

class FollowupTests(unittest.TestCase):
    def test_expired_history_still_validates_conflicting_event_ids(self):
        from repeat_resistant_briefs.history import normalize_history
        row={'url':'https://e/x', 'delivered_at':'2026-07-01', 'event_id':'v1',
             'follow_up':{'event_id':'v2', 'what_changed':'release',
                          'why_it_matters':'fix', 'evidence_url':'https://e/proof'}}
        with self.assertRaisesRegex(ValueError, r'history\[0\].*event'):
            normalize_history([row], as_of='2026-07-03', window_days=1)

    def select(self, candidate, history, **kwargs):
        self.assertTrue(hasattr(briefs,'select_result'))
        return briefs.select_result([candidate],history,**kwargs)
    def test_event_replay_and_new_event(self):
        c={'id':'new','title':'x','url':'https://e/x','quality':9,'relevance':9,'follow_up':{'event_id':'v2','what_changed':'new prose','why_it_matters':'important','evidence_url':'https://e/proof'}}
        h=[{'id':'old','url':'https://e/x','event_id':'v2'}]
        result=self.select(c,h)
        self.assertFalse(result.selected); self.assertEqual(result.decisions[0]['code'],'event_already_delivered')
        c['follow_up']['event_id']='v3'
        self.assertEqual(len(self.select(c,h).selected),1)
    def test_strict_reason_not_enough_compat_labeled(self):
        c={'title':'x','url':'https://e/x','quality':9,'relevance':9,'follow_up_reason':'news'}; h=[{'url':c['url']}]
        self.assertFalse(self.select(c,h).selected)
        result=self.select(c,h,strict=False)
        self.assertEqual(result.decisions[0]['code'],'unverified_follow_up')
    def test_nested_history_event_is_read_and_expired_event_is_not_active(self):
        follow={'event_id':'v2','what_changed':'release','why_it_matters':'fix','evidence_url':'https://e/proof'}
        c={'title':'x','url':'https://e/x','quality':9,'relevance':9,'follow_up':follow}
        h=[{'url':'https://e/x','follow_up':follow,'delivered_at':'2026-07-01'}]
        self.assertFalse(self.select(c,h).selected)
        self.assertTrue(self.select(c,h,as_of='2026-07-03',window_days=1).selected)

    def test_invalid_structured_followup(self):
        base={'title':'x','url':'https://e/x','quality':9,'relevance':9}
        for follow in [None,{},'reason',{'event_id':'e','what_changed':' ','why_it_matters':'x','evidence_url':'https://e/x'}]:
            with self.subTest(follow=follow), self.assertRaises(ValueError): self.select(dict(base,follow_up=follow),[])
