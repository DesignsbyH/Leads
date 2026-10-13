import json, os, sqlite3, struct, subprocess, sys, tempfile, unittest
from pathlib import Path

HOST = Path(__file__).resolve().parents[1] / 'leaddock' / 'native_host.py'
sys.path.insert(0, str(HOST.parent))
import native_host  # noqa: E402


def frame(obj):
    data = json.dumps(obj).encode()
    return struct.pack('=I', len(data)) + data


def unframe(blob):
    out = []
    while blob:
        (n,) = struct.unpack('=I', blob[:4])
        out.append(json.loads(blob[4:4 + n]))
        blob = blob[4 + n:]
    return out


class NativeHostTests(unittest.TestCase):
    """Runs the helper as a separate process, exactly like Edge/Chrome do (with the app closed)."""

    def run_host(self, *messages):
        env = dict(os.environ, LEADDOCK_DATA_DIR=self.data_dir)
        proc = subprocess.run([sys.executable, str(HOST), 'chrome-extension://gpeejmphkdjmjbdkkfalmpohbnmdpapg/'],
                              input=b''.join(frame(m) for m in messages), capture_output=True, env=env, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        return unframe(proc.stdout)

    def setUp(self):
        self.data_dir = tempfile.mkdtemp(prefix='leaddock-native-')

    def test_saves_without_the_app(self):
        biz = {'name': 'BAKO General Construction, Inc.', 'phone': '+1 773-414-1516', 'category': 'General contractor',
               'address': '10661 S Roberts Rd #102, Palos Hills, IL 60465', 'maps_url': 'https://www.google.com/maps?cid=17675777505358305332',
               'source': 'Google Maps'}
        ping, before, cap, after = self.run_host(
            {'action': 'ping'}, {'action': 'lookup', 'business': biz},
            {'action': 'capture', 'business': biz, 'crm': {'status': 'Qualified', 'note': 'No website — pitch one'}},
            {'action': 'lookup', 'business': biz})
        self.assertTrue(ping['helper'])
        self.assertFalse(before['found'])
        self.assertEqual((cap['result'], cap['lead']['status']), ('created', 'Qualified'))
        self.assertEqual(after['lead']['id'], cap['id'])
        # A second browser request is a fresh process, like in real use.
        (upd,) = self.run_host({'action': 'update', 'id': cap['id'], 'note': 'Called owner', 'note_type': 'Call'})
        self.assertEqual(upd['lead']['status'], 'Contacted')
        cx = sqlite3.connect(Path(self.data_dir) / 'leads.sqlite3')
        self.assertEqual(cx.execute('SELECT city, phone FROM leads').fetchone(), ('Palos Hills', '(773) 414-1516'))
        cx.close()

    def test_errors_are_reported_not_crashing(self):
        bad, unknown, ok = self.run_host({'action': 'capture', 'business': {'name': ''}}, {'action': 'nope'}, {'action': 'ping'})
        self.assertEqual((bad['ok'], bad['error']), (False, 'Business name is required.'))
        self.assertFalse(unknown['ok'])
        self.assertTrue(ok['ok'])

    def test_manifest_allows_only_the_leaddock_extension(self):
        m = native_host.host_manifest(r'C:\Users\me\AppData\Local\LeadDock2\native\leaddock_host.bat')
        self.assertEqual(m['name'], 'com.designsbyh.leaddock')
        self.assertEqual(m['allowed_origins'], ['chrome-extension://gpeejmphkdjmjbdkkfalmpohbnmdpapg/'])
        self.assertEqual(m['type'], 'stdio')


if __name__ == '__main__':
    unittest.main()
