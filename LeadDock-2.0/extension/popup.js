const API = 'http://127.0.0.1:18765';
const LISTS = {
  stages: ['New', 'Qualified', 'Contacted', 'Follow Up', 'Proposal', 'Won', 'Lost'],
  priorities: ['Low', 'Normal', 'High', 'Urgent'],
  activity_types: ['Note', 'Call', 'Email', 'Text', 'Visit', 'Meeting'],
};
const EDITABLE = ['name', 'category', 'phone', 'website', 'address', 'email', 'contact_name', 'rating', 'review_count', 'hours'];
const KEY_DETAILS = ['phone', 'website', 'address', 'category', 'hours', 'rating'];
const $ = id => document.getElementById(id);
const state = { key: '', api: 0, connected: false, business: null, lead: null };

function show(message, cls = '') { $('status').textContent = message; $('status').className = cls; }
function setConn(text, cls) { $('conn').textContent = text; $('conn').className = 'pill ' + cls; }
function fillSelect(select, items, value) {
  select.replaceChildren(...items.map(v => new Option(v, v)));
  if (value && items.includes(value)) select.value = value;
}
function localDate(daysAhead) {
  const d = new Date();
  d.setDate(d.getDate() + daysAhead);
  return d.toLocaleDateString('en-CA'); // YYYY-MM-DD in the local time zone
}
function niceDate(iso) {
  if (!iso) return '';
  const d = new Date(iso.length <= 10 ? iso + 'T12:00:00' : iso.replace(' ', 'T'));
  return isNaN(d) ? iso : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
}
function placeKey() { return state.business ? (state.business.place_id || state.business.maps_url || state.business.name) : ''; }

async function api(path, body) {
  let res;
  try {
    res = await fetch(API + path, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-LeadDock-Key': state.key },
      body: JSON.stringify(body), signal: AbortSignal.timeout(8000),
    });
  } catch (e) {
    state.connected = false;
    setConn('Desktop app offline', 'bad');
    throw new Error('LeadDock desktop app is not running. Start it with Start-LeadDock.bat, then try again.');
  }
  let data = {};
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (res.status === 403) {
    setConn('Key rejected', 'bad');
    $('settings').classList.remove('hidden');
  }
  if (!res.ok) throw new Error(data.error || `LeadDock returned an error (${res.status})`);
  return data;
}

async function checkConnection() {
  try {
    const res = await fetch(API + '/health', { signal: AbortSignal.timeout(2500) });
    const health = await res.json();
    state.connected = true;
    state.api = health.api || 2;
    for (const k of Object.keys(LISTS)) if (Array.isArray(health[k])) LISTS[k] = health[k];
    if (!state.key) {
      setConn('Pairing key needed', 'warn');
      $('settings').classList.remove('hidden');
    } else if (state.api < 3) {
      setConn('Restart LeadDock app', 'warn');
    } else {
      setConn('Connected', 'ok');
    }
  } catch (e) {
    state.connected = false;
    setConn('Desktop app offline', 'bad');
  }
}

async function readPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https:\/\/([a-z0-9-]+\.)*google\.[a-z.]+\//i.test(tab.url || '')) {
    throw new Error('Open a business in Google Maps (or a business profile in Google Search), then click LeadDock again.');
  }
  let result;
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['extractor.js'] });
    const [injected] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => globalThis.leadDockExtract() });
    result = injected && injected.result;
  } catch (e) {
    throw new Error('LeadDock could not read this tab. Reload the Google tab and try again. (' + e.message + ')');
  }
  if (!result || !result.ok) throw new Error((result && result.error) || 'No business found on this page.');
  return result;
}

function renderBusiness(result) {
  const b = state.business;
  for (const f of EDITABLE) {
    const input = $('f_' + f);
    input.value = b[f] || '';
    const missing = !input.value && KEY_DETAILS.includes(f);
    input.classList.toggle('missing', missing);
    if (missing) input.placeholder = 'Not on the profile — type it if you know it';
  }
  $('hoursBox').open = false;
  $('hoursBox').querySelector('summary').textContent = b.hours ? `Hours (${b.hours.split('\n').length} days)` : 'Hours (not listed)';

  const chips = [];
  const found = KEY_DETAILS.filter(f => b[f]).length;
  chips.push([`Found ${found} of ${KEY_DETAILS.length} key details`, found >= 5 ? 'good' : '']);
  if (!b.website) chips.push(['No website — hot lead', 'hot']);
  if (b.claimed === 'No') chips.push(['Unclaimed Google profile', 'hot']);
  if (/closed/i.test(b.business_status || '')) chips.push([b.business_status, 'bad']);
  const reviews = parseInt(String(b.review_count || '').replace(/\D/g, ''), 10);
  if (!isNaN(reviews) && reviews < 10) chips.push([`Only ${reviews} review${reviews === 1 ? '' : 's'}`, 'hot']);
  if (b.rating && parseFloat(b.rating) < 4) chips.push([`Rated ${b.rating}`, '']);
  chips.push([b.source || 'Google', '']);
  $('chips').replaceChildren(...chips.map(([text, cls]) => {
    const span = document.createElement('span');
    span.className = 'chip ' + cls;
    span.textContent = text;
    return span;
  }));
  $('limited').classList.toggle('hidden', !result.limited);
}

function renderLead() {
  const lead = state.lead;
  const banner = $('banner');
  const write = (cls, headline, body, hint) => {
    const b = document.createElement('b'); b.textContent = headline + ' ';
    const h = document.createElement('div'); h.className = 'muted'; h.textContent = hint || '';
    banner.className = 'banner ' + cls;
    banner.replaceChildren(b, document.createTextNode(body), h);
  };
  if (lead) {
    write('existing', 'Already in LeadDock.', [`Stage: ${lead.status}`, lead.priority !== 'Normal' ? `${lead.priority} priority` : '',
      lead.next_followup ? `follow up ${niceDate(lead.next_followup)}` : '',
      lead.last_contacted ? `last contacted ${niceDate(lead.last_contacted)}` : 'never contacted'].filter(Boolean).join(' · '),
      'Saving refreshes the Google details and keeps your notes.');
  } else if (state.connected && state.key && state.api >= 3) {
    write('new', 'New lead.', 'This business is not in LeadDock yet.');
  } else {
    banner.className = 'banner hidden';
  }
  fillSelect($('c_status'), LISTS.stages, lead ? lead.status : 'New');
  fillSelect($('c_priority'), LISTS.priorities, lead ? lead.priority : 'Normal');
  $('c_followup').value = lead ? lead.next_followup || '' : '';
  $('save').textContent = lead ? 'Update lead' : 'Save lead';

  const items = (lead && lead.activity) || [];
  $('activityCard').classList.toggle('hidden', !lead);
  $('activity').replaceChildren(...items.map(a => {
    const li = document.createElement('li');
    const when = document.createElement('div'); when.className = 'when'; when.textContent = niceDate(a.at);
    const what = document.createElement('span'); what.className = 'what'; what.textContent = a.action + ' ';
    const detail = document.createElement('span'); detail.textContent = a.detail;
    li.append(when, what, detail);
    return li;
  }));
  if (lead && !items.length) {
    const li = document.createElement('li'); li.className = 'muted'; li.textContent = 'No activity yet.';
    $('activity').replaceChildren(li);
  }
}

async function refreshLookup() {
  state.lead = null;
  if (state.connected && state.key && state.api >= 3) {
    try {
      const r = await api('/lookup', { business: state.business });
      state.lead = r.found ? r.lead : null;
      setConn('Connected', 'ok');
    } catch (e) { show(e.message, 'error'); }
  }
  renderLead();
}

async function loadPage() {
  $('message').textContent = 'Reading the open business profile…';
  $('message').classList.remove('hidden');
  $('main').classList.add('hidden');
  $('save').disabled = true;
  try {
    const result = await readPage();
    state.business = result.business;
    renderBusiness(result);
    $('message').classList.add('hidden');
    $('main').classList.remove('hidden');
    fillSelect($('c_note_type'), LISTS.activity_types, 'Note');
    await refreshLookup();
    const { draft } = await chrome.storage.local.get(['draft']);
    if (draft && draft.place === placeKey()) {
      $('c_note').value = draft.note || '';
      $('c_note_type').value = draft.type || 'Note';
    }
    $('save').disabled = false;
    if (!state.connected) show('Start the LeadDock desktop app to save this lead.', 'error');
  } catch (e) {
    $('message').textContent = e.message;
  }
}

function collectBusiness() {
  const b = { ...state.business };
  for (const f of EDITABLE) b[f] = $('f_' + f).value.trim();
  return b;
}

async function save() {
  $('save').disabled = true;
  show('Saving…');
  try {
    if (!state.key) throw new Error('Paste the pairing key from LeadDock → Connect browser first (⚙ above).');
    if (!state.connected) await checkConnection();
    const business = collectBusiness();
    if (!business.name) throw new Error('Business name is required.');
    const crm = {
      status: $('c_status').value, priority: $('c_priority').value, next_followup: $('c_followup').value,
      note: $('c_note').value.trim(), note_type: $('c_note_type').value,
    };
    // A LeadDock desktop app that has not been restarted since updating still expects the old format.
    const r = await api('/capture', state.api >= 3 ? { business, crm } : business);
    state.business = business;
    state.lead = r.lead || null;
    $('c_note').value = '';
    await chrome.storage.local.remove('draft');
    renderLead();
    const changed = (r.changes || []).map(c => `${c.field}: ${c.old || '—'} → ${c.new}`).join('\n');
    show((r.result === 'created' ? `✓ New lead saved: ${r.name}` : `✓ Updated: ${r.name}`) + (changed ? '\n' + changed : ''), 'ok');
  } catch (e) {
    show(e.message, 'error');
  } finally {
    $('save').disabled = false;
  }
}

$('save').onclick = save;
$('rescan').onclick = () => { show(''); loadPage(); };
$('toggleSettings').onclick = () => $('settings').classList.toggle('hidden');
$('showKey').onclick = () => { const k = $('key'); k.type = k.type === 'password' ? 'text' : 'password'; $('showKey').textContent = k.type === 'password' ? 'Show' : 'Hide'; };
$('saveKey').onclick = async () => {
  state.key = $('key').value.trim();
  await chrome.storage.local.set({ pairingKey: state.key });
  await checkConnection();
  if (state.connected && state.key) {
    show('Pairing key saved.', 'ok');
    if (state.business) await refreshLookup();
    if ($('conn').textContent === 'Connected') $('settings').classList.add('hidden');
  } else {
    show('Key saved, but the LeadDock desktop app is not running.', 'error');
  }
};
$('openApp').onclick = async () => {
  try { if (state.lead) await api('/focus', { id: state.lead.id }); } catch (e) { show(e.message, 'error'); }
};
for (const b of document.querySelectorAll('.quick button')) {
  b.onclick = () => { $('c_followup').value = b.dataset.days ? localDate(Number(b.dataset.days)) : ''; };
}
// Keep a half-written note if the popup closes (clicking the page closes extension popups).
for (const id of ['c_note', 'c_note_type']) {
  $(id).addEventListener('input', () => chrome.storage.local.set({ draft: { place: placeKey(), note: $('c_note').value, type: $('c_note_type').value } }));
}
$('c_note').addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) save(); });

(async function init() {
  const stored = await chrome.storage.local.get(['pairingKey']);
  state.key = stored.pairingKey || '';
  $('key').value = state.key;
  await checkConnection();
  await loadPage();
})();
