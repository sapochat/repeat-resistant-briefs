import unittest
from repeat_resistant_briefs.briefs import canonical_url, select_candidates, build_source_pack

class BriefTests(unittest.TestCase):
    def test_canonical_url(self):
        self.assertEqual(canonical_url("https://www.example.com/x/?utm_source=a&b=2"), "https://example.com/x?b=2")
        self.assertEqual(canonical_url("www.example.com/x/?utm_source=a&b=2"), "https://example.com/x?b=2")
        self.assertEqual(canonical_url("https://example.com:443/x"), "https://example.com/x")
        self.assertEqual(canonical_url("http://example.com:80/x"), "http://example.com/x")
        self.assertEqual(canonical_url("https://example.com:8443/x"), "https://example.com:8443/x")
    def test_canonical_url_preserves_ipv6_brackets(self):
        self.assertEqual(canonical_url("https://[2001:db8::1]/x"), "https://[2001:db8::1]/x")
    def test_canonical_url_removes_default_port_from_ipv6_host(self):
        self.assertEqual(canonical_url("https://[2001:db8::1]:443/x"), "https://[2001:db8::1]/x")
        self.assertEqual(canonical_url("http://[2001:db8::1]:80/x"), "http://[2001:db8::1]/x")
    def test_canonical_url_preserves_non_default_port_on_ipv6_host(self):
        self.assertEqual(canonical_url("https://[2001:db8::1]:8443/x"), "https://[2001:db8::1]:8443/x")
    def test_repeat_suppressed_without_reason(self):
        c=[{"id":"x","title":"X","url":"https://e/x","quality":9,"relevance":9}]
        selected,suppressed=select_candidates(c,[{"id":"x","url":"https://e/x"}])
        self.assertEqual(selected, []); self.assertEqual(len(suppressed),1)
    def test_followup_survives(self):
        c=[{"id":"x","title":"X","url":"https://e/x","quality":9,"relevance":9,"follow_up_reason":"Material update"}]
        selected,_=select_candidates(c,[{"id":"x","url":"https://e/x"}])
        self.assertTrue(selected[0]["repeat"])
        self.assertIn("FOLLOW-UP", build_source_pack(c,[{"id":"x","url":"https://e/x"}]))
    def test_equivalent_url_forms_match_history(self):
        c=[{"title":"X","url":"www.example.com/x","quality":9,"relevance":9}]
        selected,suppressed=select_candidates(c,[{"url":"https://example.com:443/x"}])
        self.assertEqual(selected, [])
        self.assertEqual(len(suppressed),1)
    def test_invalid_ports_do_not_crash_candidate_selection(self):
        c=[{"title":"X","url":"https://example.com:bad/x","quality":9,"relevance":9}]
        selected,suppressed=select_candidates(c,[{"url":"https://example.com:99999/x"}])
        self.assertEqual(len(selected),1)
        self.assertEqual(suppressed, [])

if __name__ == "__main__": unittest.main()
