import json, os, sys, tempfile, time, unittest, urllib.error, urllib.request
from pathlib import Path

os.environ['LEADDOCK_DATA_DIR'] = tempfile.mkdtemp(prefix='leaddock-bridge-')
os.environ['no_proxy'] = os.environ['NO_PROXY'] = '127.0.0.1,localhost'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'leaddock'))
import bridge, store  # noqa: E402

KEY = 'test-key'


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store.init_db()
        cls.events = []
        cls.server = bridge.start_server(KEY, lambda *e: cls.events.append(e), port=0)
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def call(self, path, body=None, key=KEY):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', 'X-LeadDock-Key': key})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_flow(self):
        status, health = self.call('/health')
        self.assertEqual((status, health['api']), (200, 3))
        biz = {'name': 'Ace Roofing', 'phone': '217-555-0123', 'maps_url': 'https://www.google.com/maps?cid=42', 'source': 'Google Maps'}
        status, found = self.call('/lookup', {'business': biz})
        self.assertEqual((status, found['found']), (200, False))

        status, cap = self.call('/capture', {'business': biz, 'crm': {'status': 'Qualified', 'note': 'Old site'}})
        self.assertEqual((status, cap['result'], cap['lead']['status']), (200, 'created', 'Qualified'))
        self.assertEqual(cap['lead']['activity'][0]['detail'], 'Old site')
        # The app is notified on the server thread just after the response is sent.
        deadline = time.time() + 2
        while ('capture', cap['id'], 'created') not in self.events and time.time() < deadline:
            time.sleep(0.01)
        self.assertIn(('capture', cap['id'], 'created'), self.events)

        status, found = self.call('/lookup', {'business': {'name': 'Ace Roofing', 'maps_url': 'https://www.google.com/maps?cid=42'}})
        self.assertEqual((found['found'], found['lead']['id']), (True, cap['id']))

        status, upd = self.call('/update', {'id': cap['id'], 'note': 'Called, no answer', 'note_type': 'Call'})
        self.assertEqual((status, upd['lead']['status']), (200, 'Contacted'))

        status, err = self.call('/update', {'id': cap['id'], 'status': 'Nope'})
        self.assertEqual(status, 400)

    def test_legacy_2_0_payload(self):
        status, cap = self.call('/capture', {'name': 'Legacy Co', 'phone': '217-555-0999',
                                             'maps_url': 'https://www.google.com/maps/place/Legacy+Co/@1,2,3z'})
        self.assertEqual((status, cap['result']), (200, 'created'))

    def test_rejects_bad_key(self):
        status, body = self.call('/capture', {'business': {'name': 'x'}}, key='wrong')
        self.assertEqual(status, 403)


if __name__ == '__main__':
    unittest.main()
