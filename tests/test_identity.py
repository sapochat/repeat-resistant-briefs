import unittest
from repeat_resistant_briefs.briefs import canonical_url

class IdentityTests(unittest.TestCase):
    def test_reject_malformed_escapes_and_spaces_before_canonicalizing(self):
        for profile in ('legacy', 'conservative'):
            for suffix in ('/x%ZZ', '/x%', '/x%2', '/x y', '/x?q=a b',
                           '/x?utm_source=%ZZ', '/x?gclid=%', '/x#bad%',
                           '/x?%ZZ=ok', '/x '):
                with self.subTest(profile=profile, suffix=suffix), self.assertRaises(ValueError):
                    canonical_url('https://e' + suffix, profile=profile)

    def test_conservative(self):
        url='https://www.Example.com/x/?z=2&ref=ok&source_id=3&utm_x=gone&a=%20#part'
        self.assertEqual(canonical_url(url,profile='conservative'),'https://www.example.com/x/?z=2&ref=ok&source_id=3&a=%20#part')
    def test_legacy_not_broad_tracking(self):
        self.assertEqual(canonical_url('https://www.e/x/?reference=1&source=2#f'),'https://e/x?reference=1&source=2')
    def test_malformed_urls(self):
        for url in ['ftp://e/x','https://u:p@e/x','https://e:bad/x','https://e:99999/x','https://e:/x','https://bad host/x','https:///x','https://e/\nx','https://-bad/x','https://[bad]/x','https://[::1]garbage/x','https://[::1]:80:90/x']:
            with self.subTest(url=url), self.assertRaises(ValueError): canonical_url(url)
    def test_schemeless_ipv6_and_default_port(self):
        self.assertEqual(canonical_url('[2001:db8::1]:443/x',profile='conservative'),'https://[2001:db8::1]/x')
