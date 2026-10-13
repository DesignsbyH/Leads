import os, sqlite3, sys, tempfile, unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix='leaddock-test-')
os.environ['LEADDOCK_DATA_DIR'] = TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'leaddock'))
import store  # noqa: E402

# Another test module may have imported store first with a different data dir; point it at ours.
store.APP_DIR = Path(TMP)
store.DB_PATH, store.KEY_PATH, store.SETTINGS_PATH = (Path(TMP) / n for n in ('leads.sqlite3', 'capture_key.txt', 'settings.json'))

MAPS_URL = ('https://www.google.com/maps/place/Steve+Ray+Plumbing+Service+Inc./@39.8278416,-90.2439712,10z/data=!4m10!1m2!2m1'
            '!1splumbers+in+Springfield+IL!3m6!1s0x88754f7254be9ce3:0xfe22527bb5918686!8m2!3d39.8278416!4d-89.63423'
            '!16s%2Fg%2F1tdh013v?entry=ttu')
CAPTURE = {
    'name': 'Steve Ray Plumbing Service Inc.', 'category': 'Plumber', 'phone': '+1 217-793-0200',
    'website': 'https://www.steverayplumbing.com/', 'address': '1501 E Griffiths Ave, Springfield, IL 62702, United States',
    'maps_url': MAPS_URL, 'rating': '4.8', 'review_count': '672', 'hours': 'Monday: Open 24 hours',
    'plus_code': 'R9H8+48 Springfield, Illinois, USA', 'source': 'Google Maps',
}


def reset():
    if store.DB_PATH.exists():
        for suffix in ('', '-wal', '-shm'):
            p = Path(str(store.DB_PATH) + suffix)
            if p.exists():
                p.unlink()
    store.init_db()


class Helpers(unittest.TestCase):
    def test_place_id_from_maps_url(self):
        self.assertEqual(store.place_id_from_url(MAPS_URL), 'cid:18312289726122526342')
        self.assertEqual(store.place_id_from_url('https://www.google.com/maps?cid=123'), 'cid:123')
        self.assertEqual(store.place_id_from_url('https://maps.google.com/x!16s%2Fg%2F11abc'), 'mid:/g/11abc')

    def test_format_phone(self):
        self.assertEqual(store.format_phone('+1 217-793-0200'), '(217) 793-0200')
        self.assertEqual(store.format_phone('Phone: 217.793.0200'), '(217) 793-0200')
        self.assertEqual(store.format_phone('+44 20 7946 0958'), '+44 20 7946 0958')

    def test_parse_address(self):
        self.assertEqual(store.parse_address('1501 E Griffiths Ave, Springfield, IL 62702, United States'),
                         {'city': 'Springfield', 'state': 'IL', 'postal_code': '62702'})
        self.assertEqual(store.parse_address('', 'R9H8+48 Springfield, Illinois, USA'), {'city': 'Springfield', 'state': 'IL'})
        self.assertEqual(store.parse_address('1 Main St, Toronto, ON M5V 2T6, Canada')['postal_code'], 'M5V 2T6')

    def test_counts_and_ratings(self):
        self.assertEqual(store.parse_count('(1,234)'), '1234')
        self.assertEqual(store.parse_count('1.2K Google reviews'), '1200')
        self.assertEqual(store.parse_rating('4.8 stars'), '4.8')

    def test_normalize(self):
        b = store.normalize_business(CAPTURE)
        self.assertEqual(b['phone'], '(217) 793-0200')
        self.assertEqual(b['address'], '1501 E Griffiths Ave, Springfield, IL 62702')
        self.assertEqual((b['city'], b['state'], b['postal_code']), ('Springfield', 'IL', '62702'))
        self.assertEqual(b['maps_url'], 'https://www.google.com/maps?cid=18312289726122526342')
        b = store.normalize_business({'name': 'x', 'website': 'https://www.google.com/url?q=http://joes.com/&sa=U',
                                      'maps_url': 'https://evil.example/maps'})
        self.assertEqual(b['website'], 'http://joes.com/')
        self.assertEqual(b['maps_url'], '')


class Leads(unittest.TestCase):
    def setUp(self):
        reset()

    def test_capture_creates_full_lead(self):
        lead_id, result, _ = store.store_lead(CAPTURE)
        self.assertEqual(result, 'created')
        r = store.get_lead(lead_id)
        self.assertEqual(r['phone'], '(217) 793-0200')
        self.assertEqual(r['website'], 'https://www.steverayplumbing.com/')
        self.assertEqual(r['city'], 'Springfield')
        self.assertEqual(r['review_count'], '672')
        self.assertEqual(r['status'], 'New')
        acts = store.list_activities(lead_id)
        self.assertEqual(acts[0]['action'], 'Captured')
        self.assertIn('phone', acts[0]['detail'])

    def test_recapture_updates_without_touching_sales_work(self):
        lead_id, _, _ = store.store_lead(CAPTURE)
        store.update_lead(lead_id, {'status': 'Proposal', 'notes': 'Wants a new site', 'email': 'me@x.com'})
        recapture = dict(CAPTURE, maps_url=MAPS_URL.replace('10z', '17z'), review_count='700', email='')
        lead_id2, result, changes = store.store_lead(recapture)
        self.assertEqual((lead_id2, result), (lead_id, 'updated'))
        r = store.get_lead(lead_id)
        self.assertEqual((r['status'], r['notes'], r['email'], r['review_count']), ('Proposal', 'Wants a new site', 'me@x.com', '700'))
        self.assertIn(('review_count', '672', '700'), changes)

    def test_matches_by_phone_and_similar_name_without_maps_url(self):
        lead_id, _, _ = store.store_lead({'name': 'Joe’s Pizza', 'phone': '(212) 366-1182'})
        again, result, _ = store.store_lead({'name': "Joe's Pizza Inc", 'phone': '+1 212-366-1182'})
        self.assertEqual((again, result), (lead_id, 'updated'))

    def test_different_places_never_merge(self):
        a, _, _ = store.store_lead({'name': 'Chain Co', 'phone': '800-555-0100', 'maps_url': 'https://www.google.com/maps?cid=1'})
        b, result, _ = store.store_lead({'name': 'Chain Co', 'phone': '800-555-0100', 'maps_url': 'https://www.google.com/maps?cid=2'})
        self.assertNotEqual(a, b)
        self.assertEqual(result, 'created')

    def test_crm_from_popup(self):
        lead_id, _, _ = store.store_lead(CAPTURE, crm={'status': 'Qualified', 'priority': 'High', 'next_followup': '2030-01-02',
                                                       'note': 'No mobile site', 'note_type': 'Note'})
        r = store.get_lead(lead_id)
        self.assertEqual((r['status'], r['priority'], r['next_followup']), ('Qualified', 'High', '2030-01-02'))
        actions = [a['action'] for a in store.list_activities(lead_id)]
        for expected in ('Captured', 'Stage', 'Priority', 'Follow-up', 'Note'):
            self.assertIn(expected, actions)

    def test_outreach_marks_contacted(self):
        lead_id, _, _ = store.store_lead(CAPTURE)
        extra = store.add_activity(lead_id, 'Call', 'Left voicemail')
        self.assertEqual(extra['status'], 'Contacted')
        r = store.get_lead(lead_id)
        self.assertEqual(r['status'], 'Contacted')
        self.assertEqual(r['last_contacted'], store.today())
        # Later stages are never moved backwards
        store.update_lead(lead_id, {'status': 'Proposal'})
        self.assertNotIn('status', store.add_activity(lead_id, 'Email', 'Sent proposal'))

    def test_update_validation(self):
        lead_id, _, _ = store.store_lead(CAPTURE)
        with self.assertRaises(ValueError):
            store.update_lead(lead_id, {'status': 'Bogus'})
        with self.assertRaises(ValueError):
            store.update_lead(lead_id, {'next_followup': 'next tuesday'})
        self.assertEqual(store.update_lead(lead_id, {'estimated_value': '$1,500'}), {'estimated_value': 1500.0})

    def test_views(self):
        a, _, _ = store.store_lead(CAPTURE)
        b, _, _ = store.store_lead({'name': 'No Site Roofing', 'phone': '217-555-0101', 'claimed': 'No'})
        store.update_lead(a, {'next_followup': store.quick_date(-1)})
        ids = lambda view: [r['id'] for r in store.query_leads(view=view)]
        self.assertEqual(ids('Follow-ups due'), [a])
        self.assertEqual(ids('No website'), [b])
        self.assertEqual(ids('Unclaimed profiles'), [b])
        self.assertEqual(set(ids('Never contacted')), {a, b})
        self.assertEqual([r['id'] for r in store.query_leads(search='roofing')], [b])
        counts = store.view_counts()
        self.assertEqual((counts['All leads'], counts['Follow-ups due'], counts['No website'], counts['Unclaimed profiles']), (2, 1, 1, 1))
        store.update_lead(a, {'status': 'Won'})
        self.assertEqual(ids('Follow-ups due'), [])
        self.assertEqual([r['id'] for r in store.query_leads(stage='Won')], [a])

    def test_website_scan_results(self):
        lead_id, _, _ = store.store_lead(CAPTURE)
        store.apply_website_scan(lead_id, {'emails': ['info@steveray.com'], 'socials': ['https://facebook.com/steveray'],
                                           'issues': ['No HTTPS'], 'audit': 'HTTPS: No'})
        r = store.get_lead(lead_id)
        self.assertEqual((r['email'], r['social_links'], r['website_issues']), ('info@steveray.com', 'https://facebook.com/steveray', 'No HTTPS'))
        self.assertEqual(store.list_activities(lead_id)[0]['action'], 'Website scan')

    def test_csv_round_trip_with_aliases(self):
        path = Path(TMP) / 'in.csv'
        path.write_text('Business Name,Phone Number,Zip Code,Stage\nAcme Lawn,217-555-0199,62704,Contacted\n', encoding='utf-8')
        self.assertEqual(store.import_csv(path), (1, 0, 0))
        r = store.query_leads()[0]
        self.assertEqual((r['name'], r['phone'], r['postal_code'], r['status'], r['source']),
                         ('Acme Lawn', '(217) 555-0199', '62704', 'Contacted', 'CSV import'))
        out = Path(TMP) / 'out.csv'
        self.assertEqual(store.export_csv(out), 1)
        self.assertEqual(store.import_csv(out), (0, 1, 0))


class Migration(unittest.TestCase):
    def test_upgrades_a_2_0_database_in_place(self):
        for suffix in ('', '-wal', '-shm'):
            p = Path(str(store.DB_PATH) + suffix)
            if p.exists():
                p.unlink()
        cx = sqlite3.connect(store.DB_PATH)
        cx.execute('''CREATE TABLE leads(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL DEFAULT '', category TEXT DEFAULT '',
        phone TEXT DEFAULT '', website TEXT DEFAULT '', address TEXT DEFAULT '', maps_url TEXT DEFAULT '',
        email TEXT DEFAULT '', contact_name TEXT DEFAULT '', city TEXT DEFAULT '', rating TEXT DEFAULT '',
        review_count TEXT DEFAULT '', status TEXT DEFAULT 'New', priority TEXT DEFAULT 'Normal',
        estimated_value REAL DEFAULT 0, next_followup TEXT DEFAULT '', notes TEXT DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        cx.execute('''CREATE TABLE activities(id INTEGER PRIMARY KEY AUTOINCREMENT,
           lead_id INTEGER NOT NULL, action TEXT NOT NULL, detail TEXT DEFAULT '', at TEXT NOT NULL)''')
        cx.execute("INSERT INTO leads(name, maps_url, address, status, notes, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                   ('Steve Ray Plumbing Service Inc.', MAPS_URL, '1501 E Griffiths Ave, Springfield, IL 62702', 'Contacted',
                    'old note', '2025-01-01 00:00:00', '2025-01-01 00:00:00'))
        cx.commit()
        cx.close()
        store.init_db()
        r = store.query_leads()[0]
        self.assertEqual((r['status'], r['notes'], r['place_id'], r['city']), ('Contacted', 'old note', 'cid:18312289726122526342', 'Springfield'))
        # A fresh capture of the same business now updates the old record instead of duplicating it.
        lead_id, result, _ = store.store_lead(CAPTURE)
        self.assertEqual((lead_id, result), (r['id'], 'updated'))
        self.assertEqual(store.get_lead(lead_id)['phone'], '(217) 793-0200')


if __name__ == '__main__':
    unittest.main()
