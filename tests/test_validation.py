import unittest
from repeat_resistant_briefs.briefs import select_candidates

class ValidationTests(unittest.TestCase):
    def surrogate_rows(self):
        base={'title':'x','url':'https://e/x','quality':9,'relevance':9}
        for bad in ('\ud800', '\udfff'):
            for field in ('title', 'substance', 'source'):
                yield dict(base, **{field:bad})
            yield dict(base, metadata={'unknown':[bad]})
            yield dict(base, metadata={bad:'value'})
            yield dict(base, **{bad:'unknown value'})

    def test_json_boundary_rejects_surrogate_keys_and_values(self):
        import json
        from repeat_resistant_briefs.validation import loads_json
        for row in self.surrogate_rows():
            with self.subTest(row=row), self.assertRaises(ValueError):
                loads_json(json.dumps([row]))

    def test_library_boundary_rejects_surrogate_keys_and_values(self):
        from repeat_resistant_briefs.validation import stable_json, validate_rows
        for row in self.surrogate_rows():
            with self.subTest(row=row, boundary='stable_json'), self.assertRaises(ValueError):
                stable_json(row)
            for kind in ('candidates', 'history'):
                with self.subTest(row=row, kind=kind), self.assertRaisesRegex(ValueError, rf'{kind}\[0\]'):
                    validate_rows([row], kind=kind)

    def test_demo_surrogate_failure_does_not_write_partial_outputs(self):
        import importlib.util
        import json
        from pathlib import Path
        import tempfile
        script=Path(__file__).resolve().parents[1] / 'examples/multi-run/run.py'
        spec=importlib.util.spec_from_file_location('surrogate_demo', script)
        assert spec is not None and spec.loader is not None
        demo=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        for row in self.surrogate_rows():
            with self.subTest(row=row), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                days=root/'days.json'
                output=root/'output'
                good={'title':'first','url':'https://e/first','quality':9,'relevance':9}
                days.write_text(json.dumps([{'date':'2026-07-01','candidates':[good]},
                                            {'date':'2026-07-02','candidates':[row]}]), encoding='utf-8')
                with self.assertRaises(ValueError):
                    demo.run(days, output)
                self.assertFalse(output.exists(), 'validation must fail before creating outputs')

    def test_valid_unicode_keeps_stable_ascii_json(self):
        from repeat_resistant_briefs.validation import loads_json, stable_json
        self.assertEqual(stable_json({'é':'😀'}), '{"\\u00e9":"\\ud83d\\ude00"}')
        self.assertEqual(loads_json('{"\\u00e9":"\\ud83d\\ude00"}'), {'é':'😀'})

    def test_invalid_shapes_and_values(self):
        base={'title':'x','url':'https://e/x','quality':9,'relevance':9}
        cases=[None,{},[None],[{}]]
        for key,values in {'title':['',None,3], 'url':['',None,'ftp://e/x'], 'id':['',None,3], 'quality':[True,'9',float('nan'),float('inf'),-1,11], 'relevance':[False,11], 'follow_up_reason':[None,3]}.items():
            cases += [[dict(base, **{key:value})] for value in values]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                select_candidates(rows,[])
    def test_errors_identify_row_and_field(self):
        good={'title':'x','url':'https://e/x','quality':9,'relevance':9}
        with self.assertRaisesRegex(ValueError,r'candidates\[1\].*title'):
            select_candidates([good,dict(good,title=None)],[])
        with self.assertRaisesRegex(ValueError,r'candidates\[0\].*quality'):
            select_candidates([dict(good,quality=float('nan'))],[])
        with self.assertRaisesRegex(ValueError,r'candidates\[0\].*follow_up.evidence_url'):
            select_candidates([dict(good,follow_up={'event_id':'e','what_changed':'x','why_it_matters':'y','evidence_url':'ftp://e/x'})],[])
        with self.assertRaisesRegex(ValueError,r'history\[0\].*delivered_at'):
            select_candidates([],[{'url':'https://e/x','delivered_at':'bad'}])
        with self.assertRaisesRegex(ValueError,r'history\[0\].*URL'):
            select_candidates([],[{'url':'https://e:bad/x'}])

    def test_limit(self):
        for limit in [-1,True,1.5,'2']:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                select_candidates([],[],limit)
    def test_json_rejects_nonfinite_duplicates_and_bad_utf8(self):
        from repeat_resistant_briefs import validation
        for text in ['[NaN]','[Infinity]','[{"a":1,"a":2}]',b'\xff']:
            with self.subTest(text=text), self.assertRaises(ValueError): validation.loads_json(text)
