"""Website scanner: visits a lead's own website to find contact details and obvious website problems.

Only the business's public pages are fetched (homepage plus up to two contact/about pages on the same site).
Nothing is sent anywhere else.
"""
import html, re, ssl, time, urllib.error, urllib.request
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 LeadDock'
MAX_BYTES = 2_000_000
EMAIL_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}')
JUNK_EMAIL = re.compile(r'\.(png|jpe?g|gif|webp|svg|css|js)$|@(example|domain|email|yourdomain|yoursite|website|test)\.|'
                        r'@([\w-]+\.)*(wixpress\.com|sentry\.io|sentry-next\.wixpress\.com)$|'
                        r'^(name|yourname|youremail|your\.email|user|username|email|john\.?doe|jane\.?doe)@', re.I)
SOCIAL = [  # (host regex, path regex marking a share/utility link, path segments that identify the profile)
    (r'(^|\.)facebook\.com$|(^|\.)fb\.com$', r'^/(sharer|share|dialog|plugins|tr|login|privacy|policies)', 1),
    (r'(^|\.)instagram\.com$', r'^/(p|reel|explore|accounts)/', 1),
    (r'(^|\.)linkedin\.com$', r'^/(share|shareArticle|sharing)', 2),
    (r'(^|\.)(twitter|x)\.com$', r'^/(intent|share|home)', 1),
    (r'(^|\.)youtube\.com$', r'^/(embed|watch|iframe_api)', 2),
    (r'(^|\.)tiktok\.com$', r'^/(embed|share)', 1),
    (r'(^|\.)yelp\.com$', r'^/(writeareview|signup)', 2),
    (r'(^|\.)nextdoor\.com$', r'^/(login|join)', 2),
    (r'(^|\.)pinterest\.com$', r'^/pin/', 1),
]
PLATFORMS = [  # (name, regex over page html + headers)
    ('Wix', r'static\.wixstatic\.com|wix\.com|x-wix-'), ('Squarespace', r'squarespace\.com|static1\.squarespace'),
    ('GoDaddy Website Builder', r'img1\.wsimg\.com|godaddy website builder|websites\.godaddy'),
    ('Shopify', r'cdn\.shopify\.com|shopify\.theme'), ('Weebly', r'weebly\.com|editmysite\.com'),
    ('Webflow', r'webflow\.(com|io)|data-wf-page'), ('Duda', r'irp\.cdn-website\.com|dudaone|multiscreensite'),
    ('WordPress', r'wp-content|wp-includes|wordpress'), ('Joomla', r'/media/jui/|joomla'), ('Drupal', r'drupal'),
    ('Google Sites', r'sites\.google\.com'), ('Hostinger Builder', r'zyrosite|hostinger'),
    ('Jimdo', r'jimdo'), ('Strikingly', r'strikingly'), ('Carrd', r'carrd\.co'), ('HubSpot', r'hs-scripts|hubspot'),
]
NOT_A_WEBSITE = {  # "websites" that are really just a profile somewhere else
    'facebook.com': 'Facebook page', 'm.facebook.com': 'Facebook page', 'instagram.com': 'Instagram profile',
    'linktr.ee': 'Linktree page', 'yelp.com': 'Yelp listing', 'business.site': 'Google free site',
    'nextdoor.com': 'Nextdoor page', 'sites.google.com': 'Google Sites page', 'g.page': 'Google profile link',
}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.meta, self.cfemails, self._title, self.title, self._in_title = [], {}, [], [], '', False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or '') for k, v in attrs}
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'].strip())
        elif tag == 'meta':
            key = (a.get('name') or a.get('property') or a.get('http-equiv') or '').lower()
            if key:
                self.meta[key] = a.get('content', '')
        elif tag == 'title':
            self._in_title = True
        if a.get('data-cfemail'):
            self.cfemails.append(a['data-cfemail'])
        if tag == 'a' and '/cdn-cgi/l/email-protection#' in a.get('href', ''):
            self.cfemails.append(a['href'].split('#', 1)[1])

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
            self.title = ' '.join(''.join(self._title).split())[:200]

    def handle_data(self, data):
        if self._in_title:
            self._title.append(data)


def decode_cfemail(hexstr):
    """Cloudflare 'email protection' hides addresses as XOR-encoded hex; many small-business sites use it."""
    try:
        key = int(hexstr[:2], 16)
        return ''.join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))
    except ValueError:
        return ''


def fetch(url, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
                                               'Accept-Language': 'en-US,en;q=0.8'})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        raw = resp.read(MAX_BYTES)
        charset = resp.headers.get_content_charset() or 'utf-8'
        headers = '\n'.join(f'{k}: {v}' for k, v in resp.headers.items()).lower()
        return {'url': resp.geturl(), 'status': resp.status, 'elapsed': time.monotonic() - started,
                'html': raw.decode(charset, errors='replace'), 'headers': headers}


def fetch_with_fallback(url, timeout):
    """Fetch, falling back to plain http:// when the site's HTTPS certificate is broken (itself worth noting).

    Returns (page, problem). A problem starting with 'Could not scan' is inconclusive rather than a website issue.
    """
    try:
        return fetch(url, timeout), None
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 406, 429, 503):
            return None, f'Could not scan: the site blocks automated visits (HTTP {e.code}); check it in your browser'
        return None, f'Website is broken (HTTP {e.code})'
    except urllib.error.URLError as e:
        reason = getattr(e, 'reason', e)
        if isinstance(reason, ssl.SSLError) or 'CERTIFICATE' in str(reason).upper():
            if url.startswith('https://'):
                try:
                    page = fetch('http://' + url[8:], timeout)
                    page['cert_error'] = True
                    return page, None
                except Exception:
                    pass
            return None, 'HTTPS certificate is invalid'
        return None, 'Website did not respond (' + str(reason)[:80] + ')'
    except (TimeoutError, OSError) as e:
        return None, 'Website did not respond (' + str(e)[:80] + ')'
    except Exception as e:  # malformed URLs, odd encodings, protocol errors
        return None, 'Could not scan: ' + str(e)[:80]


def social_profile(href):
    try:
        u = urlparse(href)
    except ValueError:
        return None
    host = (u.hostname or '').lower().removeprefix('www.').removeprefix('m.')
    for host_re, skip_re, keep in SOCIAL:
        if re.search(host_re, host) and u.path.strip('/') and not re.search(skip_re, u.path, re.I):
            parts = [p for p in u.path.split('/') if p]
            if parts[0] == 'profile.php' and 'id=' in u.query:  # facebook.com/profile.php?id=123
                return f'https://{host}/profile.php?' + next(q for q in u.query.split('&') if q.startswith('id='))
            if parts[0].startswith('@'):  # youtube.com/@handle
                keep = 1
            return f'https://{host}/' + '/'.join(parts[:keep])
    return None


def extract(page, base_domain):
    p = PageParser()
    try:
        p.feed(page['html'])
    except Exception:
        pass
    text = html.unescape(page['html'])
    emails = [decode_cfemail(h) for h in p.cfemails]
    emails += [l[7:].split('?')[0] for l in p.links if l.lower().startswith('mailto:')]
    emails += EMAIL_RE.findall(re.sub(r'<script.*?</script>', ' ', text, flags=re.S | re.I))
    phones = [re.sub(r'[^\d+]', '', l[4:]) for l in p.links if l.lower().startswith('tel:')]
    socials, internal = [], []
    for href in p.links:
        absolute = urljoin(page['url'], href)
        profile = social_profile(absolute)
        if profile:
            socials.append(profile)
        elif (urlparse(absolute).hostname or '').lower().removeprefix('www.') == base_domain:
            internal.append(absolute.split('#')[0])
    return p, emails, phones, socials, internal


def clean_emails(emails, domain):
    seen, out = set(), []
    for e in emails:
        e = e.strip().strip('.').lower()
        if not EMAIL_RE.fullmatch(e) or JUNK_EMAIL.search(e) or len(e.split('@')[0]) > 40 or e in seen:
            continue
        seen.add(e)
        out.append(e)
    # Prefer addresses on the business's own domain, then common providers.
    return sorted(out, key=lambda e: (not e.endswith('@' + domain), not e.startswith(('info@', 'contact@', 'office@', 'hello@'))))


def scan_website(url, timeout=12):
    url = url.strip()
    if url and not re.match(r'^https?://', url, re.I):
        url = 'https://' + url
    domain = (urlparse(url).hostname or '').lower().removeprefix('www.')
    result = {'url': url, 'emails': [], 'phones': [], 'socials': [], 'issues': [], 'notes': []}
    if not domain:
        result['issues'].append('No website')
        result['audit'] = 'No website on the Google profile.'
        return result
    for host, label in NOT_A_WEBSITE.items():
        if domain == host or domain.endswith('.' + host):
            result['issues'].append(f'No real website (only a {label})')
            if label.split()[0] in ('Facebook', 'Instagram', 'Yelp', 'Nextdoor'):
                result['socials'].append(social_profile(url) or url)
            result['audit'] = finish_audit(result, None)
            return result
    page, problem = fetch_with_fallback(url, timeout)
    if not page:
        result['notes' if problem.startswith('Could not scan') else 'issues'].append(problem)
        result['audit'] = finish_audit(result, None)
        return result
    final = page['url']
    domain = (urlparse(final).hostname or domain).lower().removeprefix('www.')
    p, emails, phones, socials, internal = extract(page, domain)
    pages = [final]
    # Look at a contact/about page too when the homepage has no email address.
    if not clean_emails(emails, domain):
        wanted = [l for l in dict.fromkeys(internal) if re.search(r'contact|about|reach|get-in-touch', l, re.I) and l.rstrip('/') != final.rstrip('/')]
        for link in wanted[:2]:
            extra, _ = fetch_with_fallback(link, timeout)
            if extra:
                _, e2, ph2, s2, _ = extract(extra, domain)
                emails += e2
                phones += ph2
                socials += s2
                pages.append(extra['url'])
    blob = (page['html'][:400_000] + page['headers']).lower()
    result.update(
        final_url=final, status=page['status'], elapsed=page['elapsed'], pages=pages, title=p.title,
        https=final.lower().startswith('https://') and not page.get('cert_error'), cert_error=bool(page.get('cert_error')),
        mobile='width=device-width' in p.meta.get('viewport', '').replace(' ', '').lower(),
        description=bool(p.meta.get('description', '').strip() or p.meta.get('og:description', '').strip()),
        platform=next((name for name, rx in PLATFORMS if re.search(rx, blob)), ''),
        analytics=bool(re.search(r'googletagmanager\.com|google-analytics\.com|gtag\(', blob)),
        emails=clean_emails(emails, domain), phones=list(dict.fromkeys(x for x in phones if len(re.sub(r'\D', '', x)) >= 10)),
        socials=list(dict.fromkeys(socials)),
    )
    years = [int(y) for y in re.findall(r'(?:©|&copy;|&#169;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})', page['html'], re.I)]
    result['copyright_year'] = max(years) if years else None
    if result['cert_error']:
        result['issues'].append('HTTPS certificate is invalid')
    elif not result['https']:
        result['issues'].append('No HTTPS')
    if not result['mobile']:
        result['issues'].append('Not mobile-friendly')
    if result['copyright_year'] and result['copyright_year'] <= date.today().year - 3:
        result['issues'].append(f"Outdated (© {result['copyright_year']})")
    if result['elapsed'] > 6:
        result['issues'].append(f"Slow ({result['elapsed']:.1f}s)")
    if not result['description']:
        result['issues'].append('No meta description')
    result['audit'] = finish_audit(result, page)
    return result


def finish_audit(r, page):
    yes = lambda b: 'Yes' if b else 'No'
    lines = []
    if r['issues']:
        lines.append('Issues: ' + ', '.join(r['issues']))
    lines += r.get('notes', [])
    if page:
        lines += [
            f"Loaded: HTTP {r['status']} in {r['elapsed']:.1f}s — {r['final_url']}",
            f"HTTPS: {'Certificate error' if r['cert_error'] else yes(r['https'])}",
            f"Mobile-friendly viewport: {yes(r['mobile'])}",
            f"Built with: {r['platform'] or 'Unknown / custom'}",
            f"Page title: {r['title'] or '(none)'}",
            f"Meta description: {yes(r['description'])}",
            f"Google Analytics / Tag Manager: {yes(r['analytics'])}",
            f"Copyright year: {r['copyright_year'] or 'not shown'}",
            f"Emails found: {', '.join(r['emails']) or 'none'}",
            f"Social profiles: {len(r['socials'])}",
            f"Pages checked: {len(r['pages'])}",
        ]
    return '\n'.join(lines)
