// Injected into the Google Maps / Google Search tab by popup.js. Defines globalThis.leadDockExtract(), which
// reads the business profile that is currently open and returns {ok, business} or {ok: false, error}.
// Google changes its markup often, so every field has a fallback and nothing here throws.
globalThis.leadDockExtract = function leadDockExtract() {
  const clean = s => String(s || '').replace(/[   ‎‏]/g, ' ').replace(/\s+/g, ' ').trim();
  const label = e => clean(e && e.getAttribute('aria-label'));
  const text = e => clean(e && e.textContent);
  const visible = e => !!(e && e.getClientRects().length);
  const norm = s => clean(s).toLowerCase().replace(/[^a-z0-9]/g, '');
  const sameName = (a, b) => { a = norm(a); b = norm(b); return !!a && !!b && (a === b || a.includes(b) || b.includes(a)); };
  const leaf = (root, re) => [...root.querySelectorAll('span,div,a,button')]
    .find(e => !e.children.length && re.test(clean(e.textContent)) && visible(e));
  const unwrap = href => {
    try {
      const u = new URL(href, location.href);
      if (/(^|\.)google\./.test(u.hostname) && u.pathname === '/url') return u.searchParams.get('q') || u.searchParams.get('url') || '';
      return u.href;
    } catch (e) { return ''; }
  };
  const isGoogle = href => { try { return /(^|\.)google\.[a-z.]+$/.test(new URL(href).hostname); } catch (e) { return true; } };
  const cidFromFid = fid => { try { return BigInt('0x' + fid.split(':0x')[1]).toString(); } catch (e) { return ''; } };
  const safeDecode = s => { try { return decodeURIComponent(s); } catch (e) { return s; } };
  const searchUrl = (name, address) => 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent([name, address].filter(Boolean).join(' '));
  const canonical = cid => 'https://www.google.com/maps?cid=' + cid;
  const DAY = /^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b/i;

  function hoursFromRows(rows) {
    const lines = [];
    for (const tr of rows) {
      const cells = tr.querySelectorAll('td');
      if (cells.length < 2) continue;
      const day = clean((cells[0].querySelector('div') || cells[0]).textContent);
      let hours = label(cells[1]) || [...cells[1].querySelectorAll('li')].map(text).join(', ') || text(cells[1]);
      hours = hours.replace(/,?\s*hours might differ/i, '').trim();
      if (DAY.test(day) && hours) lines.push(`${day}: ${hours}`);
    }
    return [...new Set(lines)].join('\n');
  }

  function idsFromText(s) {
    s = safeDecode(String(s || ''));
    const out = {};
    const cid = s.match(/[?&#](?:cid|ludocid)(?:=|\\u003d)(\d{5,})/i);
    const fid = s.match(/(0x[0-9a-f]{6,}:0x[0-9a-f]{6,})/i);
    if (cid) out.cid = cid[1];
    else if (fid) out.cid = cidFromFid(fid[1]);
    const mid = s.match(/!16s(\/g\/[\w-]+)/);
    if (mid) out.mid = mid[1];
    return out;
  }

  function fromMaps() {
    // When a business is opened from a search list, Maps keeps BOTH panels in the page: the "Results" list
    // and the business. Score every panel and use the business one (the old version read the list).
    let panel = null, best = 3;
    for (const m of document.querySelectorAll('div[role="main"]')) {
      const h1 = text(m.querySelector('h1'));
      let score = 0;
      if (h1 && !/^(results|search results|sponsored)$/i.test(h1)) score += 3;
      if (m.querySelector('[data-item-id]')) score += 3;
      if (label(m) && sameName(label(m), h1)) score += 2;
      if (visible(m)) score += 1;
      if (score >= best) { best = score; panel = m; }
    }
    if (!panel) return { ok: false, error: 'Click a business in the results list or on the map so its details panel opens, then try again.' };

    const name = text(panel.querySelector('h1'));
    const item = re => [...panel.querySelectorAll('[data-item-id]')].find(e => re.test(e.getAttribute('data-item-id') || ''));
    const byLabel = re => [...panel.querySelectorAll('[aria-label]')].find(e => re.test(label(e)));

    const addressEl = item(/^address$/) || byLabel(/^address:/i);
    const address = (clean(label(addressEl).replace(/^address:\s*/i, '')) || text(addressEl)).replace(/,\s*(United States|USA)$/i, '');
    const phoneEl = item(/^phone:tel:/) || byLabel(/^phone:/i);
    const phone = clean(label(phoneEl).replace(/^phone:\s*/i, '')) || clean((phoneEl && phoneEl.getAttribute('data-item-id') || '').replace(/^phone:tel:/, ''));
    const siteEl = item(/^authority$/) || byLabel(/^website:/i);
    let website = siteEl ? unwrap(siteEl.getAttribute('href') || (siteEl.closest('a') && siteEl.closest('a').getAttribute('href')) || '') : '';
    if (!website && siteEl) website = clean(label(siteEl).replace(/^website:\s*/i, ''));
    if (website && isGoogle(website)) website = '';
    if (!website) {
      // Fallback: the results list has a "Visit <name>'s website" button for businesses that list a site.
      const visit = [...document.querySelectorAll('a[aria-label][href]')]
        .find(a => { const m = label(a).match(/^visit (.+?)['’]s website$/i); return m && norm(m[1]) === norm(name); });
      if (visit) website = unwrap(visit.getAttribute('href'));
      if (website && isGoogle(website)) website = '';
    }
    const plus_code = clean(label(item(/^oloc$/)).replace(/^plus code:\s*/i, ''));

    const category = text(panel.querySelector('button[jsaction*=".category"]')) || text(panel.querySelector('button[jsaction*="category"]'));
    const header = panel.querySelector('.F7nice') || panel;
    const imgs = [...header.querySelectorAll('[role="img"][aria-label]')];
    const ratingImg = imgs.find(e => /^\d(?:[.,]\d)?\s+stars?/i.test(label(e)));
    const reviewImg = imgs.find(e => /^[\d,.]+\s+reviews?/i.test(label(e)));
    let rating = ((ratingImg && label(ratingImg)) || text(header.querySelector('span[aria-hidden="true"]')) || '').match(/\d(?:[.,]\d)?/);
    let reviews = ((reviewImg && label(reviewImg)) || '').match(/[\d,.]+/) || (text(header).match(/\(([\d,.]+K?)\)/) || [])[1];
    if (!reviews) {
      // The panel can hide the review count; the same business's entry in the results list usually still shows
      // "4.8 stars 672 Reviews".
      const entry = [...document.querySelectorAll('[role="feed"] a[aria-label]')].find(a => sameName(label(a), name));
      const box = entry && entry.parentElement;
      const stars = box && [...box.querySelectorAll('[role="img"][aria-label]')].map(label).find(l => /stars?\s+[\d,.]+\s+reviews?/i.test(l));
      const m = stars && stars.match(/^(\d(?:[.,]\d)?)\s+stars?\s+([\d,.]+)\s+reviews?/i);
      if (m) { reviews = m[2]; rating = rating || [m[1]]; }
    }

    const priceEl = byLabel(/^price:/i);
    const price_level = priceEl ? (/^[$€£¥₹]/.test(text(priceEl)) ? text(priceEl) : label(priceEl).replace(/^price:\s*/i, '')) : '';
    const closed = leaf(panel, /^(permanently|temporarily) closed$/i);
    const claim = leaf(panel, /^(claim this business|own this business\??)$/i) || byLabel(/^claim this business/i);
    const hours = hoursFromRows(panel.querySelectorAll('table tr'));

    // The URL carries Google's stable place ID and exact coordinates, but only trust it when it is for this business
    // (it can lag behind when clicking quickly between results).
    const href = location.href;
    const urlName = safeDecode(((location.pathname.match(/\/maps\/place\/([^/]+)/) || [])[1] || '').replace(/\+/g, ' '));
    const urlIsThisPlace = !urlName ? /[?&]cid=/.test(href) : sameName(urlName, name) || norm(urlName) === norm(name);
    const ids = urlIsThisPlace ? idsFromText(href) : {};
    const coords = urlIsThisPlace ? [...href.matchAll(/!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)/g)].pop() : null;
    const place_id = ids.cid ? 'cid:' + ids.cid : ids.mid ? 'mid:' + ids.mid : '';

    return {
      ok: true,
      business: {
        name, category, phone, website, address, plus_code, hours,
        rating: rating ? rating[0].replace(',', '.') : '',
        review_count: reviews ? String(Array.isArray(reviews) ? reviews[0] : reviews) : '',
        price_level, business_status: closed ? text(closed) : 'Operational', claimed: claim ? 'No' : '',
        latitude: coords ? coords[1] : '', longitude: coords ? coords[2] : '', place_id,
        maps_url: ids.cid ? canonical(ids.cid) : urlIsThisPlace ? href : searchUrl(name, address),
        source: 'Google Maps',
      },
      // Signed-out visitors sometimes get Google's "limited view", which hides review counts and most hours.
      limited: !reviews && /limited view of google maps/i.test(document.body.innerText),
    };
  }

  function fromSearch() {
    // Google Search business profile ("knowledge panel"), including the panel opened from the local results.
    const titles = [...document.querySelectorAll('[data-attrid="title"]')].filter(visible);
    if (!titles.length) return { ok: false, error: 'No business profile found on this page. Open a business profile in Google Maps or Google Search.' };
    const details = '[data-attrid*="location:address"],[data-attrid*="has_phone"],[data-attrid*="location:hours"],[data-attrid*="unified_actions"]';
    let root = null, titleEl = titles[0];
    outer: for (const t of titles) {
      for (let el = t, i = 0; el && i < 20; el = el.parentElement, i++) {
        if (el.querySelector(details)) { root = el; titleEl = t; break outer; }
      }
    }
    root = root || titleEl.closest('#rhs,[role="complementary"],.kp-wholepage') || document.body;
    const attr = sel => [...root.querySelectorAll(`[data-attrid${sel}]`)].find(visible) || root.querySelector(`[data-attrid${sel}]`);
    const value = el => el ? clean(el.innerText.replace(/^[^:\n]{1,30}:\s*/, '').split('\n')[0]) : '';

    const name = clean(titleEl.innerText.split('\n')[0]);
    const subtitle = clean(attr('="subtitle"') && attr('="subtitle"').innerText);
    const category = clean(subtitle.split(/\s+in\s+/)[0]);
    const address = value(attr('*="location:address"'));
    const phoneEl = attr('*="has_phone"');
    const phoneLink = root.querySelector('[data-dtype="d3ph"], a[href^="tel:"], [aria-label^="Call phone number" i]');
    const phone = (value(phoneEl).match(/\+?[\d(][\d\s().-]{6,}\d/) || [])[0]
      || clean(label(phoneLink).replace(/^call phone number\s*/i, '')) || text(phoneLink);
    const hoursEl = attr('*="location:hours"');
    const hours = hoursEl ? hoursFromRows(hoursEl.querySelectorAll('tr')) : '';
    const siteLink = [...root.querySelectorAll('a[href]')].find(a => /^website$/i.test(clean(a.innerText)) || /^website\b/i.test(label(a)));
    let website = siteLink ? unwrap(siteLink.getAttribute('href')) : '';
    if (website && isGoogle(website)) website = '';
    const all = root.innerText || '';
    const rated = [...root.querySelectorAll('[aria-label]')].map(label).map(l => l.match(/rated\s+(\d(?:[.,]\d)?)\s+out of 5/i)).find(Boolean);
    const near = all.match(/\b([1-5][.,]\d)\b[\s\S]{0,60}?([\d,.]+K?)\s+(?:google\s+)?reviews/i);
    const reviews = all.match(/([\d,.]+K?)\s+google reviews/i) || near;
    const closed = all.match(/\b(permanently|temporarily) closed\b/i);

    let ids = idsFromText(location.href);
    if (!ids.cid) ids = Object.assign(idsFromText(root.outerHTML), ids);
    const mapsLink = root.querySelector('a[href*="/maps/place/"]');
    if (!ids.cid && mapsLink) ids = Object.assign(idsFromText(mapsLink.href), ids);
    const place_id = ids.cid ? 'cid:' + ids.cid : ids.mid ? 'mid:' + ids.mid : '';

    return {
      ok: true,
      business: {
        name, category, phone, website, address, hours,
        rating: (rated ? rated[1] : near ? near[1] : '').replace(',', '.'),
        review_count: reviews ? (reviews === near ? near[2] : reviews[1]) : '',
        business_status: closed ? clean(closed[0]).replace(/^\w/, c => c.toUpperCase()) : 'Operational',
        claimed: /own this business\?/i.test(all) ? 'No' : '', place_id,
        maps_url: ids.cid ? canonical(ids.cid) : mapsLink ? mapsLink.href : searchUrl(name, address),
        source: 'Google Search',
      },
    };
  }

  try {
    const onMaps = /^maps\.google\./i.test(location.hostname) || location.pathname.startsWith('/maps');
    return onMaps ? fromMaps() : fromSearch();
  } catch (e) {
    return { ok: false, error: 'Could not read this page: ' + e.message };
  }
};
