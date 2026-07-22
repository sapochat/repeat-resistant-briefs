import unittest
from repeat_resistant_briefs.briefs import canonical_url, select_candidates, build_source_pack

class BriefTests(unittest.TestCase):
    def test_canonical_url(self):
        self.assertEqual(canonical_url("https://www.example.com/x/?utm_source=a&b=2"), "https://example.com/x?b=2")
    def test_repeat_suppressed_without_reason(self):
        c=[{"id":"x","title":"X","url":"https://e/x","quality":9,"relevance":9}]
        selected,suppressed=select_candidates(c,[{"id":"x","url":"https://e/x"}])
        self.assertEqual(selected, []); self.assertEqual(len(suppressed),1)
    def test_followup_survives(self):
        c=[{"id":"x","title":"X","url":"https://e/x","quality":9,"relevance":9,"follow_up_reason":"Material update"}]
        selected,_=select_candidates(c,[{"id":"x","url":"https://e/x"}])
        self.assertTrue(selected[0]["repeat"])
        self.assertIn("FOLLOW-UP", build_source_pack(c,[{"id":"x","url":"https://e/x"}]))

if __name__ == "__main__": unittest.main()
