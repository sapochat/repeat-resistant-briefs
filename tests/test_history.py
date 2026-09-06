import unittest
from repeat_resistant_briefs import briefs

class HistoryTests(unittest.TestCase):
    def test_reject_out_of_range_offset_components(self):
        from repeat_resistant_briefs.history import parse_timestamp
        for offset in ('+00:99', '-00:60', '+23:60', '+24:00', '-24:00'):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                parse_timestamp('2026-07-01T00:00:00' + offset)

    def test_utc_conversion_overflow_is_indexed_field_value_error(self):
        from repeat_resistant_briefs.history import normalize_history, parse_timestamp
        for stamp in ('0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-01:00'):
            for field in ('delivered_at', 'date'):
                with self.subTest(stamp=stamp, field=field), self.assertRaisesRegex(ValueError, rf'history\[1\].*{field}'):
                    normalize_history([{'url':'https://e/ok'}, {'url':'https://e/x',field:stamp}])
            with self.subTest(as_of=stamp), self.assertRaisesRegex(ValueError, 'as_of'):
                parse_timestamp(stamp, 'as_of')

    def select(self, history, **kwargs):
        self.assertTrue(hasattr(briefs,'select_result'))
        return briefs.select_result([{'title':'x','url':'https://e/x','quality':9,'relevance':9}],history,**kwargs)
    def test_window_inclusive_utc(self):
        for stamp,selected in [('2026-07-01',False),('2026-06-30T23:59:59Z',True),('2026-07-01T01:00:00+01:00',False)]:
            with self.subTest(stamp=stamp):
                self.assertEqual(bool(self.select([{'url':'https://e/x','delivered_at':stamp}],window_days=2,as_of='2026-07-03').selected),selected)
    def test_dates_validate_without_window(self):
        for stamp in ['nonsense',None,'2026-02-30']:
            with self.subTest(stamp=stamp), self.assertRaises(ValueError): self.select([{'url':'https://e/x','delivered_at':stamp}])
        with self.assertRaises(ValueError): self.select([{'url':'https://e/x','delivered_at':'2026-07-04'}],as_of='2026-07-03')
        with self.assertRaises(ValueError): self.select([],window_days=2)
    def test_history_policy_mismatch_is_diagnostic(self):
        result=self.select([{'url':'https://e/x','canonicalization_version':'legacy-v1'}])
        self.assertTrue(any(d['code']=='canonicalization_mismatch' for d in result.diagnostics))

    def test_legacy_date_and_helpers(self):
        from repeat_resistant_briefs.history import normalize_history, window_history, parse_timestamp
        rows=[{'url':'https://e/x','date':'2026-07-01'}]
        normalized,_=normalize_history(rows)
        self.assertEqual(normalized[0]['delivered_at'],'2026-07-01T00:00:00Z')
        self.assertNotIn('delivered_at',rows[0])
        self.assertEqual(window_history(rows,as_of='2026-07-03',window_days=2)[0],normalized)
        self.assertEqual(parse_timestamp('2026-07-01').utcoffset().total_seconds(),0)

    def test_bad_window_values_and_naive_timestamp(self):
        for value in [-1,True,1.5]:
            with self.assertRaises(ValueError): self.select([],window_days=value,as_of='2026-07-03')
        with self.assertRaises(ValueError): self.select([],as_of='2026-07-03T12:00:00')

    def test_undated_active_with_diagnostic(self):
        result=self.select([{'url':'https://e/x'}],window_days=2,as_of='2026-07-03')
        self.assertFalse(result.selected)
        self.assertTrue(any(d['code']=='undated_history_active' for d in result.diagnostics))
