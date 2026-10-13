import os, sys, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'leaddock'))
import enrich  # noqa: E402

os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"


def cf(email, key=0x42):
    return f'{key:02x}' + ''.join(f'{ord(c) ^ key:02x}' for c in email)


PAGES = {
    '/': f'''<html><head><title>Ace Plumbing | Springfield IL</title>
        <meta name="generator" content="WordPress 6.1"><link rel="stylesheet" href="/wp-content/themes/x.css"></head>
        <body><a href="/contact-us/">Contact</a> <a href="https://www.facebook.com/AcePlumbingIL/">Facebook</a>
        <a href="https://www.facebook.com/sharer/sharer.php?u=x">Share</a> <a href="https://instagram.com/aceplumbing">IG</a>
        <a href="tel:+1-217-555-0100">Call</a> <img src="logo@2x.png"> <footer>&copy; 2016 Ace Plumbing</footer></body></html>''',
    '/contact-us/': f'''<html><body><a href="/cdn-cgi/l/email-protection#{cf('office@aceplumbing.com')}">email</a>
        <a href="mailto:owner@gmail.com?subject=Hi">mail</a> errors@o123.ingest.sentry.io</body></html>''',
    '/modern': '''<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="description" content="Best roofing"><script src="https://static.wixstatic.com/x.js"></script></head>
        <body>info@modernroof.com © 2020-2026</body></html>''',
}


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/blocked':
            self.send_response(403); self.end_headers(); return
        body = PAGES.get(self.path)
        if body is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


class ScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Site)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_old_site_finds_contact_details_and_issues(self):
        r = enrich.scan_website(self.base + '/')
        self.assertEqual(r['emails'], ['office@aceplumbing.com', 'owner@gmail.com'])
        self.assertIn('https://facebook.com/AcePlumbingIL', r['socials'])
        self.assertIn('https://instagram.com/aceplumbing', r['socials'])
        self.assertFalse(any('sharer' in s for s in r['socials']))
        self.assertEqual(r['phones'], ['+12175550100'])
        self.assertEqual(r['platform'], 'WordPress')
        for issue in ('No HTTPS', 'Not mobile-friendly', 'Outdated (© 2016)', 'No meta description'):
            self.assertIn(issue, r['issues'])
        self.assertEqual(len(r['pages']), 2)
        self.assertTrue(r['audit'].startswith('Issues: '))

    def test_modern_site(self):
        r = enrich.scan_website(self.base + '/modern')
        self.assertEqual(r['platform'], 'Wix')
        self.assertTrue(r['mobile'])
        self.assertEqual(r['copyright_year'], 2026)
        self.assertEqual(r['emails'], ['info@modernroof.com'])
        self.assertEqual(r['issues'], ['No HTTPS'])

    def test_broken_blocked_and_down(self):
        self.assertIn('Website is broken (HTTP 404)', enrich.scan_website(self.base + '/missing')['issues'])
        blocked = enrich.scan_website(self.base + '/blocked')
        self.assertEqual(blocked['issues'], [])
        self.assertIn('Could not scan', blocked['audit'])
        down = enrich.scan_website('http://127.0.0.1:9/', timeout=2)
        self.assertTrue(down['issues'][0].startswith('Website did not respond'))

    def test_social_page_instead_of_website(self):
        r = enrich.scan_website('https://www.facebook.com/joesplumbing')
        self.assertEqual(r['issues'], ['No real website (only a Facebook page)'])
        self.assertEqual(r['socials'], ['https://facebook.com/joesplumbing'])

    def test_no_website(self):
        self.assertEqual(enrich.scan_website('')['issues'], ['No website'])


if __name__ == '__main__':
    unittest.main()
