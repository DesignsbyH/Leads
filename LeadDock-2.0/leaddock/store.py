"""LeadDock storage: SQLite schema + migrations, capture/merge rules and the activity timeline.

Nothing in here imports Qt, so it can be used by the HTTP bridge, the website scanner and tests.
"""
import csv, json, os, re, secrets, sqlite3
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote_plus, unquote

APP_DIR = Path(os.environ.get('LEADDOCK_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'LeadDock2')
DB_PATH = APP_DIR / 'leads.sqlite3'
KEY_PATH = APP_DIR / 'capture_key.txt'
SETTINGS_PATH = APP_DIR / 'settings.json'
VERSION = '2.7'

STAGES = ['New', 'Qualified', 'Contacted', 'Follow Up', 'Proposal', 'Won', 'Lost']
CLOSED_STAGES = ('Won', 'Lost')
PRIORITIES = ['Low', 'Normal', 'High', 'Urgent']
ACTIVITY_TYPES = ['Note', 'Call', 'Email', 'Text', 'Visit', 'Meeting']
OUTREACH_TYPES = ('Call', 'Email', 'Text', 'Visit', 'Meeting')

# Column order is also the CSV export order. Everything is TEXT except the deal value.
COLUMNS = {
    'name': "TEXT NOT NULL DEFAULT ''", 'category': "TEXT DEFAULT ''", 'industry': "TEXT DEFAULT ''", 'phone': "TEXT DEFAULT ''",
    'email': "TEXT DEFAULT ''", 'website': "TEXT DEFAULT ''", 'address': "TEXT DEFAULT ''",
    'city': "TEXT DEFAULT ''", 'state': "TEXT DEFAULT ''", 'postal_code': "TEXT DEFAULT ''",
    'contact_name': "TEXT DEFAULT ''", 'maps_url': "TEXT DEFAULT ''", 'place_id': "TEXT DEFAULT ''",
    'rating': "TEXT DEFAULT ''", 'review_count': "TEXT DEFAULT ''", 'hours': "TEXT DEFAULT ''",
    'business_status': "TEXT DEFAULT ''", 'claimed': "TEXT DEFAULT ''", 'price_level': "TEXT DEFAULT ''",
    'plus_code': "TEXT DEFAULT ''", 'latitude': "TEXT DEFAULT ''", 'longitude': "TEXT DEFAULT ''",
    'social_links': "TEXT DEFAULT ''", 'website_issues': "TEXT DEFAULT ''", 'website_audit': "TEXT DEFAULT ''",
    'website_scanned_at': "TEXT DEFAULT ''", 'source': "TEXT DEFAULT ''",
    'status': "TEXT DEFAULT 'New'", 'priority': "TEXT DEFAULT 'Normal'", 'estimated_value': 'REAL DEFAULT 0',
    'next_followup': "TEXT DEFAULT ''", 'last_contacted': "TEXT DEFAULT ''", 'notes': "TEXT DEFAULT ''",
}
FIELDS = list(COLUMNS)

# Facts Google is the source of truth for: a recapture refreshes them.
GOOGLE_FACTS = ('category', 'phone', 'website', 'address', 'city', 'state', 'postal_code', 'maps_url', 'place_id',
                'rating', 'review_count', 'hours', 'business_status', 'claimed', 'price_level', 'plus_code',
                'latitude', 'longitude')
# Fields a capture/import only fills in when they are blank, so your own edits are never overwritten.
FILL_IF_BLANK = ('name', 'industry', 'email', 'contact_name', 'social_links', 'source', 'notes', 'estimated_value',
                 'next_followup', 'last_contacted')
MULTILINE = ('hours', 'social_links', 'website_audit', 'notes')
# Changes worth calling out in the timeline when a recapture modifies them.
NOTABLE = ('phone', 'website', 'address', 'category', 'business_status', 'rating', 'review_count')

LABELS = {
    'name': 'Business', 'category': 'Google category', 'industry': 'Business type', 'phone': 'Phone', 'email': 'Email', 'website': 'Website',
    'address': 'Address', 'city': 'City', 'state': 'State', 'postal_code': 'ZIP', 'contact_name': 'Contact person',
    'maps_url': 'Google Maps URL', 'place_id': 'Google place ID', 'rating': 'Rating', 'review_count': 'Reviews',
    'hours': 'Hours', 'business_status': 'Business status', 'claimed': 'Profile claimed', 'price_level': 'Price level',
    'plus_code': 'Plus code', 'latitude': 'Latitude', 'longitude': 'Longitude', 'social_links': 'Social links',
    'website_issues': 'Website issues', 'website_audit': 'Website audit', 'website_scanned_at': 'Website scanned',
    'source': 'Source', 'status': 'Stage', 'priority': 'Priority', 'estimated_value': 'Deal value',
    'next_followup': 'Follow-up', 'last_contacted': 'Last contacted', 'notes': 'Pinned notes',
}

US_STATES = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA', 'colorado': 'CO',
    'connecticut': 'CT', 'delaware': 'DE', 'district of columbia': 'DC', 'florida': 'FL', 'georgia': 'GA',
    'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS', 'kentucky': 'KY',
    'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD', 'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN',
    'mississippi': 'MS', 'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH',
    'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND',
    'ohio': 'OH', 'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI',
    'south carolina': 'SC', 'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
    'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY',
    'puerto rico': 'PR',
}

# Broad business types for filtering ("call my church leads"), derived from Google's very specific categories
# ("Baptist church", "Roofing contractor"...). Checked in order, first match wins, so specific rules come first.
INDUSTRY_RULES = [
    ('Church & Religious', r'church|chapel|cathedral|parish|ministr|mosque|synagogue|temple|place of worship|worship|religious|'
                           r'gospel|bible|tabernacle|congregation|diocese|monaster|convent|kingdom hall'),
    ('Nonprofit & Community', r'food bank|food pantry|non-?profit|charity|homeless shelter'),
    ('Dental', r'dent(ist|al)|orthodont|endodont|periodont|oral surgeon'),
    ('Pets & Veterinary', r'veterinar|animal (hospital|clinic|shelter)|\bpets?\b|groomer|\bdogs?\b|kennel|\bcat (hospital|boarding)'),
    ('Beauty & Wellness', r'salon|barber|\bspa\b|\bnails?\b|beauty|\bhair|cosmet|eyelash|\blash|\bbrow|waxing|massage|tattoo|piercing|'
                          r'tanning|esthetic|aesthetic|makeup|wellness'),
    ('Medical & Health', r'medical|doctor|physician|clinic|hospital|chiropract|physical therap|urgent care|optometr|ophthalm|eye care|'
                         r'pharmac|counsel|therapist|psycholog|psychiatr|mental health|nursing|health|pediatric|dermatolog|surgeon|'
                         r'podiatr|acupunct|rehab|hospice|laborator|imaging|audiolog|retirement|assisted living|senior living'),
    ('Roofing', r'roof'),
    ('Plumbing', r'plumb|drain|sewer|septic|water heater'),
    ('HVAC', r'hvac|heating|air condition|furnace|\bac\b|cooling|ventilat|air duct|ductwork'),
    ('Electrical & Solar', r'electric|solar|generator'),
    ('Painting', r'paint(er|ing)'),
    ('Landscaping & Lawn', r'landscap|lawn|tree (service|trimm|remov)|arborist|garden|irrigation|snow remov|plant nursery|\bsod\b'),
    ('Cleaning', r'clean|janitor|maid|pressure wash|power wash|restoration|water damage|mold'),
    ('Pest Control', r'pest|extermin|termite|wildlife (control|removal)|bed bug'),
    ('Construction & Remodeling', r'contractor|construct|builder|remodel|renovat|carpent|concrete|mason|drywall|framing|excavat|'
                                  r'paving|asphalt|\bdeck|fence|fencing contractor|handyman|handyperson|home improvement|cabinet|countertop|'
                                  r'floor|\btil(e|ing)\b|siding|gutter|insulation|demolition|foundation|waterproof|stucco|weld|'
                                  r'architect|engineer|survey'),
    ('Home Services', r'locksmith|appliance|garage door|\bpools?\b|spa repair|moving|movers?\b|storage|security system|alarm|'
                      r'home inspect|chimney|junk|dumpster|hauling|window|blinds|shutter|interior design|upholster|hot tub'),
    ('Auto', r'\bauto|\bcar\b|\bcars\b|vehicle|mechanic|\btires?\b|collision|body shop|oil change|towing|tow truck|transmission|'
             r'motorcycle|\brv\b|truck repair|smog|emission|detailing'),
    ('Restaurants & Food', r'restaurant|caf[eé]|coffee|bakery|pizza|grill|diner|cater|food|deli\b|taco|sushi|burger|\bbar\b|\bpub\b|'
                           r'brew|winery|tavern|bistro|ice cream|donut|doughnut|juice|tea house|steak|bbq|barbecue|kitchen'),
    ('Legal', r'lawyer|attorney|law firm|legal|notary|bail bond'),
    ('Finance & Insurance', r'accountant|accounting|\btax|\bcpa\b|bookkeep|insurance|financ|\bbank|credit union|mortgage|loan|'
                            r'investment|wealth|payroll'),
    ('Real Estate', r'real estate|realtor|property manag|apartment|condominium|housing|rental agency|title company|appraiser'),
    ('Fitness & Recreation', r'\bgym|fitness|yoga|pilates|martial art|karate|taekwondo|jiu|boxing|crossfit|danc|golf|bowling|sports|'
                             r'recreation|trampoline|swim|tennis|skating|climbing'),
    ('Education & Childcare', r'school|academy|tutor|day ?care|child ?care|preschool|learning|college|universit|education|training|'
                              r'lesson|montessori|kindergarten'),
    ('Events & Hospitality', r'hotel|motel|\binn\b|bed & breakfast|lodging|resort|event|venue|wedding|banquet|photograph|videograph|'
                             r'\bdj\b|party|entertain|limousine|travel'),
    ('Government & Public', r'city hall|government|county|department of|police|fire station|post office|library|courthouse|\bdmv\b'),
    ('Professional Services', r'marketing|advertis|consult|agency|printing|print shop|\bsigns?\b|graphic|web|design|software|'
                              r'computer|technolog|staffing|employment|recruit|business|office|copy|courier|translation|answering'),
    ('Nonprofit & Community', r'community|association|social serv|shelter|volunteer|\bclub\b|lodge|veterans|foundation'),
    ('Manufacturing & Industrial', r'manufactur|machine shop|fabricat|wholesale|distribut|warehouse|supplier|industrial|factory|'
                                   r'trucking|freight|logistic|recycl|metal|plastic|\bmill\b'),
    ('Retail & Shops', r'store|shop|boutique|florist|jewel|gift|furniture|hardware|clothing|outlet|market|mall|liquor|thrift|pawn|vape'),
]
INDUSTRIES = list(dict.fromkeys(name for name, _ in INDUSTRY_RULES)) + ['Other']


def industry_for(category, name=''):
    """Broad business type for a Google category (falls back to the business name, e.g. "Grace Bible Church")."""
    for text, from_name in ((category, False), ('' if category else name, True)):
        text = (text or '').lower()
        for industry, pattern in INDUSTRY_RULES if text else ():
            # A name like "Smith Business Group" says little; only trust specific trades when guessing from names.
            if from_name and industry == 'Professional Services':
                continue
            if re.search(pattern, text):
                return industry
    return 'Other'


# CSV headers from other tools (Google Sheets exports, scrapers, LeadDock 1.0) mapped to LeadDock fields.
CSV_ALIASES = {
    'business': 'name', 'business_name': 'name', 'company': 'name', 'company_name': 'name', 'title': 'name',
    'phone_number': 'phone', 'telephone': 'phone', 'tel': 'phone', 'url': 'website', 'site': 'website',
    'web': 'website', 'website_url': 'website', 'e_mail': 'email', 'email_address': 'email',
    'zip': 'postal_code', 'zip_code': 'postal_code', 'zipcode': 'postal_code', 'postcode': 'postal_code',
    'full_address': 'address', 'street_address': 'address', 'stage': 'status', 'pipeline_stage': 'status',
    'google_maps_url': 'maps_url', 'maps_link': 'maps_url', 'google_maps': 'maps_url', 'reviews': 'review_count',
    'reviews_count': 'review_count', 'stars': 'rating', 'contact': 'contact_name', 'contact_person': 'contact_name',
    'follow_up': 'next_followup', 'followup': 'next_followup', 'deal_value': 'estimated_value', 'value': 'estimated_value',
    'type': 'category', 'business_type': 'industry', 'sector': 'industry', 'note': 'notes', 'socials': 'social_links',
}


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def today():
    return date.today().isoformat()


def get_key():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not KEY_PATH.exists():
        KEY_PATH.write_text(secrets.token_urlsafe(32), encoding='utf-8')
    return KEY_PATH.read_text(encoding='utf-8').strip()


def load_settings():
    defaults = {'auto_scan_websites': True}
    try:
        defaults.update(json.loads(SETTINGS_PATH.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
    return defaults


def save_settings(settings):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding='utf-8')


@contextmanager
def db():
    """A connection that commits on success, rolls back on error and is always closed."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(DB_PATH, timeout=15)
    cx.row_factory = sqlite3.Row
    cx.execute('PRAGMA busy_timeout=15000')
    try:
        with cx:
            yield cx
    finally:
        cx.close()


def init_db():
    with db() as cx:
        cx.execute('PRAGMA journal_mode=WAL')
        cx.execute('''CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        cx.execute('''CREATE TABLE IF NOT EXISTS activities(id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL, action TEXT NOT NULL, detail TEXT DEFAULT '', at TEXT NOT NULL,
            FOREIGN KEY(lead_id) REFERENCES leads(id))''')
        # Add any columns this version introduced; existing leads keep all of their data.
        have = {r['name'] for r in cx.execute('PRAGMA table_info(leads)')}
        for col, decl in COLUMNS.items():
            if col not in have:
                cx.execute(f'ALTER TABLE leads ADD COLUMN {col} {decl.replace("NOT NULL ", "")}')
        cx.execute('CREATE INDEX IF NOT EXISTS leads_name ON leads(name)')
        cx.execute('CREATE INDEX IF NOT EXISTS leads_stage ON leads(status)')
        cx.execute('CREATE INDEX IF NOT EXISTS leads_place ON leads(place_id)')
        cx.execute('CREATE INDEX IF NOT EXISTS activities_lead ON activities(lead_id, at)')
        # Older captures stored only the long Maps URL; derive the stable place ID so recaptures match them.
        for r in cx.execute("SELECT id, maps_url, address, city FROM leads WHERE place_id='' OR place_id IS NULL").fetchall():
            pid = place_id_from_url(r['maps_url'])
            if pid:
                cx.execute('UPDATE leads SET place_id=? WHERE id=?', (pid, r['id']))
        for r in cx.execute("SELECT id, category, name FROM leads WHERE industry='' OR industry IS NULL").fetchall():
            cx.execute('UPDATE leads SET industry=? WHERE id=?', (industry_for(r['category'], r['name']), r['id']))
        for r in cx.execute("SELECT id, address FROM leads WHERE address!='' AND (city='' OR city IS NULL)").fetchall():
            parts = parse_address(r['address'])
            if parts.get('city'):
                cx.execute('UPDATE leads SET city=?, state=?, postal_code=? WHERE id=?',
                           (parts['city'], parts.get('state', ''), parts.get('postal_code', ''), r['id']))


# ---------------------------------------------------------------- normalising helpers

def clean_url(s):
    s = (s or '').strip()
    if s and not re.match(r'^https?://', s, re.I):
        s = 'https://' + s
    return s


def is_google_host(url):
    try:
        host = urlparse(url).hostname or ''
    except ValueError:
        return False
    return bool(re.search(r'(^|\.)google\.[a-z]{2,3}(\.[a-z]{2})?$', host, re.I))


def unwrap_google_redirect(url):
    """Google wraps outbound links as https://www.google.com/url?q=<real url>."""
    if is_google_host(url) and urlparse(url).path == '/url':
        qs = parse_qs(urlparse(url).query)
        return (qs.get('q') or qs.get('url') or [url])[0]
    return url


def site_domain(url):
    try:
        return (urlparse(clean_url(url)).hostname or '').lower().removeprefix('www.')
    except ValueError:
        return ''


def phone_digits(s):
    return re.sub(r'\D', '', s or '')[-10:]


def format_phone(s):
    """US/Canada numbers become (217) 793-0200; anything else is kept as Google showed it."""
    s = re.sub(r'^(phone|call|telephone|tel)\s*:?\s*', '', (s or '').strip(), flags=re.I)
    digits = re.sub(r'\D', '', s)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) == 10 and (not s.startswith('+') or s.startswith('+1')):
        return f'({digits[:3]}) {digits[3:6]}-{digits[6:]}'
    return s


def norm_name(s):
    s = re.sub(r'[^a-z0-9 ]', '', (s or '').lower().replace('&', ' and '))
    s = re.sub(r'\b(the|inc|llc|ltd|co|corp|company|incorporated)\b', ' ', s)
    return re.sub(r'\s+', '', s)


def similar_names(a, b):
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 5 and (a in b or b in a))


def place_id_from_url(url):
    """Stable Google identifier for a place: its CID ('cid:123…') or knowledge-graph id ('mid:/g/…')."""
    url = unquote(url or '')
    m = re.search(r'[?&](?:cid|ludocid)=(\d+)', url)
    if m:
        return 'cid:' + m.group(1)
    m = re.search(r'!1s0x[0-9a-f]+:0x([0-9a-f]+)', url, re.I)
    if m:
        return 'cid:' + str(int(m.group(1), 16))
    m = re.search(r'!16s(/g/[\w-]+|/m/[\w-]+)', url)
    if m:
        return 'mid:' + m.group(1)
    return ''


def canonical_maps_url(place_id, fallback=''):
    if place_id.startswith('cid:'):
        return 'https://www.google.com/maps?cid=' + place_id[4:]
    return fallback


def parse_address(address, plus_code=''):
    """Split a Google-formatted address into city/state/ZIP (US and Canada; best effort elsewhere)."""
    a = re.sub(r',?\s*(United States|USA|US|Canada)\s*$', '', (address or '').strip(), flags=re.I)
    parts = [p.strip() for p in a.split(',') if p.strip()]
    if len(parts) >= 2:
        last = parts[-1]
        m = re.match(r'^([A-Z]{2})\s+(\d{5}(?:-\d{4})?|[A-Z]\d[A-Z] ?\d[A-Z]\d)$', last)
        if m:
            return {'city': parts[-2], 'state': m.group(1), 'postal_code': m.group(2)}
        if re.fullmatch(r'[A-Z]{2}', last):
            return {'city': parts[-2], 'state': last}
        if last.lower() in US_STATES:
            return {'city': parts[-2], 'state': US_STATES[last.lower()]}
    if plus_code:  # e.g. "R9H8+48 Springfield, Illinois, USA" for businesses without a street address
        pc = re.sub(r'^[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{0,3}\s*', '', plus_code.strip(), flags=re.I)
        pc_parts = [p.strip() for p in re.sub(r',?\s*(USA|United States)$', '', pc).split(',') if p.strip()]
        if pc_parts:
            state = pc_parts[1] if len(pc_parts) > 1 else ''
            return {'city': pc_parts[0], 'state': US_STATES.get(state.lower(), state)}
    return {}


def parse_count(s):
    """'1,234' / '(672)' / '1.2K reviews' -> '1234' / '672' / '1200'."""
    m = re.search(r'(\d[\d,.]*)\s*([kK])?', str(s or ''))
    if not m:
        return ''
    num = m.group(1).rstrip('.,')
    if m.group(2):
        try:
            return str(int(float(num.replace(',', '')) * 1000))
        except ValueError:
            return ''
    return re.sub(r'\D', '', num)


def parse_rating(s):
    m = re.search(r'\b([0-5](?:[.,]\d)?)\b', str(s or ''))
    return m.group(1).replace(',', '.') if m else ''


def valid_date(s):
    s = (s or '').strip()
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date().isoformat() if s else ''
    except ValueError:
        return ''


def normalize_business(data):
    """Turn a capture/import payload into clean LeadDock field values (unknown keys are dropped)."""
    out = {}
    for k in FIELDS:
        v = data.get(k, '')
        v = '' if v is None else str(v)
        out[k] = v.strip() if k in MULTILINE else re.sub(r'\s+', ' ', v).strip()
    out['name'] = out['name'][:250]
    out['website'] = clean_url(unwrap_google_redirect(out['website']))
    if is_google_host(out['website']):
        out['website'] = ''
    out['maps_url'] = clean_url(out['maps_url'])
    if out['maps_url'] and not is_google_host(out['maps_url']):
        out['maps_url'] = ''
    out['place_id'] = out['place_id'] or place_id_from_url(out['maps_url'])
    if out['place_id'] and not re.match(r'^(cid|mid):', out['place_id']):
        out['place_id'] = place_id_from_url(out['place_id']) or ('cid:' + out['place_id'] if out['place_id'].isdigit() else '')
    out['maps_url'] = canonical_maps_url(out['place_id'], out['maps_url'])
    out['phone'] = format_phone(out['phone'])
    out['address'] = re.sub(r',?\s*(United States|USA)\s*$', '', out['address'], flags=re.I)
    out['plus_code'] = re.sub(r'^plus code\s*:\s*', '', out['plus_code'], flags=re.I)
    if not out['city']:
        for k, v in parse_address(out['address'], out['plus_code']).items():
            out[k] = out[k] or v
    out['industry'] = out['industry'] or industry_for(out['category'], out['name'])
    out['rating'] = parse_rating(out['rating'])
    out['review_count'] = parse_count(out['review_count'])
    out['email'] = re.sub(r'^mailto:', '', out['email'], flags=re.I).split('?')[0]
    out['next_followup'] = valid_date(out['next_followup'])
    out['last_contacted'] = valid_date(out['last_contacted'])
    try:
        out['estimated_value'] = float(re.sub(r'[^\d.\-]', '', out['estimated_value']) or 0)
    except ValueError:
        out['estimated_value'] = 0.0
    return out


# ---------------------------------------------------------------- leads

def find_existing(cx, biz):
    """Match a capture to an existing lead: Google place ID, then Maps URL, phone, address, website."""
    if biz['place_id']:
        row = cx.execute('SELECT * FROM leads WHERE place_id=?', (biz['place_id'],)).fetchone()
        if row:
            return row
    if biz['maps_url']:
        row = cx.execute('SELECT * FROM leads WHERE maps_url=?', (biz['maps_url'],)).fetchone()
        if row:
            return row

    def compatible(row):  # two different Google places are never the same lead
        return not (biz['place_id'] and row['place_id'] and row['place_id'] != biz['place_id'])

    digits = phone_digits(biz['phone'])
    if len(digits) == 10:
        for row in cx.execute("SELECT * FROM leads WHERE phone!=''"):
            if phone_digits(row['phone']) == digits and similar_names(row['name'], biz['name']) and compatible(row):
                return row
    if biz['address']:
        for row in cx.execute('SELECT * FROM leads WHERE address=? COLLATE NOCASE', (biz['address'],)):
            if similar_names(row['name'], biz['name']) and compatible(row):
                return row
    domain = site_domain(biz['website'])
    if domain:
        for row in cx.execute("SELECT * FROM leads WHERE website!=''"):
            if site_domain(row['website']) == domain and similar_names(row['name'], biz['name']) and compatible(row):
                return row
    return None


def _log(cx, lead_id, action, detail='', at=None):
    cx.execute('INSERT INTO activities(lead_id, action, detail, at) VALUES(?,?,?,?)', (lead_id, action, detail, at or now()))


def describe_capture(biz):
    found = [LABELS[k].lower() for k in ('phone', 'website', 'address', 'hours', 'category', 'email') if biz.get(k)]
    bits = [('Found ' + ', '.join(found)) if found else 'Only the name was found']
    if biz.get('rating'):
        bits.append(f"rated {biz['rating']}" + (f" ({biz['review_count']} reviews)" if biz.get('review_count') else ''))
    if not biz.get('website'):
        bits.append('no website listed')
    if biz.get('claimed') == 'No':
        bits.append('profile not claimed')
    return '; '.join(bits)


def store_lead(data, crm=None):
    """Create or refresh a lead from a capture/import. Returns (lead_id, 'created'|'updated', changes).

    `crm` holds explicit choices made while capturing (status, priority, next_followup, note, note_type) and
    is applied after the business facts so stage changes are logged in the timeline.
    """
    biz = normalize_business(data)
    if not biz['name']:
        raise ValueError('Business name is required.')
    source = biz['source'] or 'Manual'
    changes = []
    with db() as cx:
        row = find_existing(cx, biz)
        if row:
            lead_id, result = row['id'], 'updated'
            updates = {}
            for k in GOOGLE_FACTS:
                if biz[k] and str(biz[k]) != str(row[k] or ''):
                    updates[k] = biz[k]
            for k in FILL_IF_BLANK:
                if biz[k] and not row[k]:
                    updates[k] = biz[k]
            if updates:
                updates['updated_at'] = now()
                cx.execute('UPDATE leads SET ' + ','.join(f'{k}=?' for k in updates) + ' WHERE id=?', (*updates.values(), lead_id))
            changes = [(k, row[k] or '', updates[k]) for k in NOTABLE if k in updates]
            other = [LABELS[k].lower() for k in updates if k != 'updated_at' and k not in NOTABLE]
            detail = '; '.join([f"{LABELS[k]}: {old or '—'} → {new}" for k, old, new in changes] + (['updated ' + ', '.join(other)] if other else []))
            if detail:  # re-saving an unchanged profile (e.g. just to log a call) adds no timeline noise
                _log(cx, lead_id, 'Refreshed', f'{source}: {detail}')
        else:
            result = 'created'
            biz['status'] = biz['status'] if biz['status'] in STAGES else 'New'
            biz['priority'] = biz['priority'] if biz['priority'] in PRIORITIES else 'Normal'
            biz['source'] = source
            columns = FIELDS + ['created_at', 'updated_at']
            values = [biz[k] for k in FIELDS] + [now(), now()]
            lead_id = cx.execute(f'INSERT INTO leads ({",".join(columns)}) VALUES ({",".join("?" * len(values))})', values).lastrowid
            _log(cx, lead_id, 'Captured', f'{source}: {describe_capture(biz)}')
    if crm:
        apply_crm(lead_id, crm)
    return lead_id, result, changes


def apply_crm(lead_id, crm):
    """Stage/priority/follow-up/note chosen in the browser extension popup."""
    updates = {k: crm[k] for k in ('status', 'priority', 'industry') if crm.get(k)}
    if crm.get('next_followup') is not None:
        updates['next_followup'] = crm['next_followup']
    if updates:
        update_lead(lead_id, updates)
    note = str(crm.get('note') or '').strip()
    if note:
        add_activity(lead_id, crm.get('note_type') or 'Note', note)


def update_lead(lead_id, changes, log=True):
    """Save edited fields. Stage, priority and follow-up changes are written to the timeline."""
    clean = {}
    for k, v in changes.items():
        if k not in COLUMNS:
            continue
        v = '' if v is None else v
        if k == 'status' and v not in STAGES:
            raise ValueError(f'Unknown stage: {v}')
        if k == 'priority' and v not in PRIORITIES:
            raise ValueError(f'Unknown priority: {v}')
        if k == 'name' and not str(v).strip():
            raise ValueError('Business name cannot be blank.')
        if k == 'estimated_value':
            try:
                v = float(re.sub(r'[^\d.\-]', '', str(v)) or 0)
            except ValueError:
                raise ValueError('Deal value must be a number.')
        elif k in ('next_followup', 'last_contacted'):
            if str(v).strip() and not valid_date(str(v)):
                raise ValueError('Dates must look like 2026-10-31.')
            v = valid_date(str(v))
        elif k == 'place_id':
            v = str(v).strip()
        elif k not in MULTILINE:
            v = str(v).strip()
        clean[k] = v
    with db() as cx:
        row = cx.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
        if not row:
            raise ValueError('That lead no longer exists.')
        clean = {k: v for k, v in clean.items() if str(v) != str(row[k] if row[k] is not None else '')}
        if not clean:
            return {}
        if ({'category', 'name'} & set(clean)) and 'industry' not in clean and (row['industry'] or 'Other') == 'Other':
            guess = industry_for(clean.get('category', row['category']), clean.get('name', row['name']))
            if guess != 'Other':  # a lead you typed in by hand gets its type once you give it a name/category
                clean['industry'] = guess
        cx.execute('UPDATE leads SET ' + ','.join(f'{k}=?' for k in clean) + ',updated_at=? WHERE id=?', (*clean.values(), now(), lead_id))
        if log:
            if 'status' in clean:
                _log(cx, lead_id, 'Stage', f"{row['status'] or 'New'} → {clean['status']}")
            if 'priority' in clean:
                _log(cx, lead_id, 'Priority', f"{row['priority'] or 'Normal'} → {clean['priority']}")
            if 'next_followup' in clean:
                when = datetime.strptime(clean['next_followup'], '%Y-%m-%d').strftime('%a %b %d, %Y') if clean['next_followup'] else ''
                _log(cx, lead_id, 'Follow-up', f'Set for {when}' if when else 'Cleared')
    return clean


def add_activity(lead_id, action, detail='', status=None, next_followup=None):
    """Log a note/call/email/etc., optionally moving the stage and setting the follow-up in the same step.

    Logging outreach records the contact date and, unless a stage is given, moves New/Qualified leads to Contacted.
    Returns the lead fields that changed so the caller can tell the user about them.
    """
    action = action if action in ACTIVITY_TYPES else 'Note'
    detail = (detail or '').strip()
    if action == 'Note' and not detail:
        raise ValueError('Write a note first.')
    if status and status not in STAGES:
        raise ValueError(f'Unknown stage: {status}')
    extra = {}
    with db() as cx:
        row = cx.execute('SELECT status, next_followup FROM leads WHERE id=?', (lead_id,)).fetchone()
        if not row:
            raise ValueError('That lead no longer exists.')
        _log(cx, lead_id, action, detail)
        if action in OUTREACH_TYPES:
            extra['last_contacted'] = today()
            if not status and row['status'] in ('New', 'Qualified', '', None):
                status = 'Contacted'
        if status and status != row['status']:
            extra['status'] = status
            _log(cx, lead_id, 'Stage', f"{row['status'] or 'New'} → {status}")
        if next_followup is not None and valid_date(next_followup) != (row['next_followup'] or ''):
            extra['next_followup'] = valid_date(next_followup)
            when = date.fromisoformat(extra['next_followup']).strftime('%a %b %d, %Y') if extra['next_followup'] else ''
            _log(cx, lead_id, 'Follow-up', f'Set for {when}' if when else 'Cleared')
        cx.execute('UPDATE leads SET ' + ''.join(f'{k}=?,' for k in extra) + 'updated_at=? WHERE id=?', (*extra.values(), now(), lead_id))
    return extra


# Call outcomes for one-click logging: label -> (activity type, stage to move to, follow-up in N days; '' clears it)
CALL_OUTCOMES = {
    'No answer': ('Call', None, 2),
    'Left voicemail': ('Call', None, 3),
    'Interested': ('Call', 'Follow Up', 1),
    'Call back later': ('Call', 'Follow Up', 7),
    'Sent proposal': ('Email', 'Proposal', 3),
    'Not interested': ('Call', 'Lost', ''),
    'Wrong number / closed': ('Call', 'Lost', ''),
}


def outcome_plan(outcome, current_status):
    """(activity type, stage or None, follow-up date or '' or None) for a call outcome.

    Stages only ever move forward automatically (a Proposal lead that says "call back later" stays a Proposal);
    Lost is the exception.
    """
    kind, stage, days = CALL_OUTCOMES[outcome]
    if stage and stage != 'Lost' and current_status in STAGES and STAGES.index(current_status) >= STAGES.index(stage):
        stage = None
    followup = '' if days == '' else quick_date(days) if days is not None else None
    return kind, stage, followup


def update_activity(activity_id, detail):
    with db() as cx:
        cx.execute('UPDATE activities SET detail=? WHERE id=?', ((detail or '').strip(), activity_id))


def delete_activity(activity_id):
    with db() as cx:
        cx.execute('DELETE FROM activities WHERE id=?', (activity_id,))


def get_lead(lead_id):
    with db() as cx:
        return cx.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()


def list_activities(lead_id, limit=500):
    with db() as cx:
        return cx.execute('SELECT * FROM activities WHERE lead_id=? ORDER BY at DESC, id DESC LIMIT ?', (lead_id, limit)).fetchall()


def delete_leads(ids):
    ids = list(ids)
    if not ids:
        return
    marks = ','.join('?' * len(ids))
    with db() as cx:
        cx.execute(f'DELETE FROM activities WHERE lead_id IN ({marks})', ids)
        cx.execute(f'DELETE FROM leads WHERE id IN ({marks})', ids)


def lookup(data):
    biz = normalize_business(data)
    with db() as cx:
        return find_existing(cx, biz)


def lead_summary(lead_id, activity_limit=5):
    row = get_lead(lead_id)
    if not row:
        return None
    out = {k: row[k] for k in ('id', 'name', 'industry', 'status', 'priority', 'next_followup', 'last_contacted', 'notes',
                               'email', 'website_issues', 'created_at', 'updated_at')}
    out['activity'] = [{'action': a['action'], 'detail': a['detail'], 'at': a['at']} for a in list_activities(lead_id, activity_limit)]
    return out


OPEN_SQL = "status NOT IN ('Won','Lost')"
VIEW_SQL = {  # view name -> WHERE clause; ':today' is bound to today's date
    'All leads': '1=1',
    'Follow-ups due': f"next_followup!='' AND next_followup<=:today AND {OPEN_SQL}",
    'Never contacted': f"(last_contacted='' OR last_contacted IS NULL) AND {OPEN_SQL}",
    'No website': "(website='' OR website IS NULL)",
    'Website issues': "website_issues!='' AND website_issues IS NOT NULL",
    'Unclaimed profiles': "claimed='No'",
    'High priority': f"priority IN ('High','Urgent') AND {OPEN_SQL}",
    'Open deals': OPEN_SQL,
}
VIEWS = list(VIEW_SQL)
SEARCH_COLUMNS = ['name', 'phone', 'email', 'website', 'city', 'state', 'address', 'category', 'industry', 'contact_name', 'notes']
INDUSTRY_SQL = "COALESCE(NULLIF(industry,''),'Other')"
CITY_SQL = "TRIM(COALESCE(city,'') || CASE WHEN COALESCE(state,'')!='' AND COALESCE(city,'')!='' THEN ', ' || state ELSE '' END)"
# The latest note/call/email you logged, shown in the lead list.
LAST_NOTE_SQL = """(SELECT a.action || ': ' || a.detail FROM activities a WHERE a.lead_id=leads.id
                    AND a.action IN ('Note','Call','Email','Text','Visit','Meeting') ORDER BY a.at DESC, a.id DESC LIMIT 1)"""


def lead_filter(search='', stage='All stages', view='All leads', industry='', city='', skip=()):
    """WHERE clause + args for the lead list. `skip` leaves out filters (used to count each facet's options)."""
    where, args = [], {'today': today()}
    if 'view' not in skip:
        where.append(VIEW_SQL.get(view, '1=1'))
    for i, term in enumerate((search or '').split()):
        where.append('(' + ' OR '.join(f'{c} LIKE :t{i}' for c in SEARCH_COLUMNS) + ')')
        args[f't{i}'] = '%' + term + '%'
    if stage in STAGES and 'stage' not in skip:
        where.append('status=:stage')
        args['stage'] = stage
    if industry and 'industry' not in skip:
        where.append(f'{INDUSTRY_SQL}=:industry')
        args['industry'] = industry
    if city and 'city' not in skip:
        where.append(f'{CITY_SQL}=:city')
        args['city'] = city
    return ' AND '.join(where) or '1=1', args


def query_leads(search='', stage='All stages', view='All leads', industry='', city=''):
    where, args = lead_filter(search, stage, view, industry, city)
    order = 'next_followup ASC, updated_at DESC' if view == 'Follow-ups due' else 'updated_at DESC'
    with db() as cx:
        return cx.execute(f'SELECT leads.*, {LAST_NOTE_SQL} AS last_note FROM leads WHERE {where} ORDER BY {order}', args).fetchall()


def facet_counts(search='', stage='All stages', view='All leads', industry='', city=''):
    """How many leads each filter option would show, given the other active filters."""
    f = dict(search=search, stage=stage, view=view, industry=industry, city=city)
    out = {}
    with db() as cx:
        where, args = lead_filter(**f, skip=('view',))
        cols = ', '.join(f'SUM(CASE WHEN {sql} THEN 1 ELSE 0 END)' for sql in VIEW_SQL.values())
        row = cx.execute(f'SELECT {cols} FROM leads WHERE {where}', args).fetchone()
        out['views'] = {name: row[i] or 0 for i, name in enumerate(VIEW_SQL)}
        where, args = lead_filter(**f, skip=('industry',))
        out['industries'] = [(r[0], r[1]) for r in cx.execute(
            f'SELECT {INDUSTRY_SQL} k, COUNT(*) n FROM leads WHERE {where} GROUP BY k ORDER BY n DESC, k', args)]
        where, args = lead_filter(**f, skip=('stage',))
        counts = dict(cx.execute(f'SELECT status, COUNT(*) FROM leads WHERE {where} GROUP BY status', args).fetchall())
        out['stages'] = [(s, counts.get(s, 0)) for s in STAGES]
        where, args = lead_filter(**f, skip=('city',))
        out['cities'] = [(r[0], r[1]) for r in cx.execute(
            f'SELECT {CITY_SQL} k, COUNT(*) n FROM leads WHERE {where} GROUP BY k ORDER BY n DESC, k', args)]
    return out


def view_counts():
    return facet_counts()['views']


def industries_in_use():
    with db() as cx:
        used = [r[0] for r in cx.execute(f'SELECT DISTINCT {INDUSTRY_SQL} FROM leads')]
    return INDUSTRIES[:-1] + sorted(set(used) - set(INDUSTRIES)) + ['Other']


def pipeline_summary():
    with db() as cx:
        rows = {r['status']: r for r in cx.execute('SELECT status, COUNT(*) n, COALESCE(SUM(estimated_value),0) value FROM leads GROUP BY status')}
        total = cx.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
        due = cx.execute(f"SELECT COUNT(*) FROM leads WHERE {VIEW_SQL['Follow-ups due']}", {'today': today()}).fetchone()[0]
    return [(s, rows[s]['n'] if s in rows else 0, rows[s]['value'] if s in rows else 0) for s in STAGES], total, due


def apply_website_scan(lead_id, scan):
    """Store a website scan result: fills a blank email/phone, merges social links, records the audit."""
    row = get_lead(lead_id)
    if not row:
        return {}
    updates = {'website_audit': scan.get('audit', ''), 'website_issues': ', '.join(scan.get('issues', [])),
               'website_scanned_at': now()}
    if scan.get('emails') and not row['email']:
        updates['email'] = scan['emails'][0]
    if scan.get('phones') and not row['phone']:
        updates['phone'] = format_phone(scan['phones'][0])
    links = [l for l in (row['social_links'] or '').splitlines() if l.strip()]
    for link in scan.get('socials', []):
        if link not in links:
            links.append(link)
    updates['social_links'] = '\n'.join(links)
    update_lead(lead_id, updates, log=False)
    found = []
    if 'email' in updates:
        found.append('email ' + updates['email'])
    if scan.get('socials'):
        found.append(f"{len(scan['socials'])} social link(s)")
    detail = ('Found ' + ', '.join(found) + '. ' if found else '') + (('Issues: ' + updates['website_issues']) if updates['website_issues'] else 'No major issues found.')
    with db() as cx:
        _log(cx, lead_id, 'Website scan', detail)
    return updates


# ---------------------------------------------------------------- CSV

def export_csv(path, rows=None):
    if rows is None:
        with db() as cx:
            rows = cx.execute('SELECT * FROM leads ORDER BY name').fetchall()
    cols = ['id'] + FIELDS + ['created_at', 'updated_at']
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for r in rows:
            writer.writerow([r[c] for c in cols])
    return len(rows)


def import_csv(path):
    created = updated = skipped = 0
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        for raw in csv.DictReader(f):
            row = {}
            for k, v in raw.items():
                key = re.sub(r'[^a-z0-9]+', '_', (k or '').strip().lower()).strip('_')
                key = CSV_ALIASES.get(key, key)
                if key in COLUMNS and v not in (None, '') and not row.get(key):
                    row[key] = v
            row.setdefault('source', 'CSV import')
            try:
                _, result, _ = store_lead(row)
                created += result == 'created'
                updated += result == 'updated'
            except Exception:
                skipped += 1
    return created, updated, skipped


def followup_label(value):
    """'Overdue 3d' / 'Today' / 'Tomorrow' / 'Fri Oct 17' for the lead table."""
    d = valid_date(value)
    if not d:
        return ''
    days = (date.fromisoformat(d) - date.today()).days
    if days < 0:
        return f'Overdue {-days}d'
    if days == 0:
        return 'Today'
    if days == 1:
        return 'Tomorrow'
    return date.fromisoformat(d).strftime('%a %b %d') if days < 300 else d


def quick_date(days):
    return (date.today() + timedelta(days=days)).isoformat()


def maps_search_url(name, address=''):
    return 'https://www.google.com/maps/search/?api=1&query=' + quote_plus(' '.join(x for x in (name, address) if x))


# ---------------------------------------------------------------- changes made by the browser helper

def change_stamp():
    """Cheap fingerprint of the database; changes whenever a lead or timeline entry is added or edited."""
    with db() as cx:
        return tuple(cx.execute('SELECT COUNT(*), MAX(updated_at), MAX(id), (SELECT MAX(id) FROM activities) FROM leads').fetchone())


def lead_ids_after(lead_id):
    with db() as cx:
        return [r[0] for r in cx.execute('SELECT id FROM leads WHERE id>? ORDER BY id', (lead_id or 0,))]


def unscanned_captures():
    """Leads captured from Google whose website hasn't been scanned yet (e.g. saved while the app was closed)."""
    with db() as cx:
        return [r[0] for r in cx.execute("""SELECT id FROM leads WHERE website!='' AND (website_scanned_at='' OR website_scanned_at IS NULL)
                                            AND source LIKE 'Google%' ORDER BY id""")]
