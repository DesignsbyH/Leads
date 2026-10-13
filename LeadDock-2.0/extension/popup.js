// Uses transport.js (loaded first) to reach LeadDock: helper first, then the open desktop app, else queue the lead.
const LISTS = {
  stages: ['New', 'Qualified', 'Contacted', 'Follow Up', 'Proposal', 'Won', 'Lost'],
  priorities: ['Low', 'Normal', 'High', 'Urgent'],
  activity_types: ['Note', 'Call', 'Email', 'Text', 'Visit', 'Meeting'],
};
const EDITABLE = ['name', 'category', 'phone', 'website', 'address', 'email', 'contact_name', 'rating', 'review_count', 'hours'];
const KEY_DETAILS = ['phone', 'website', 'address', 'category', 'hours', 'rating'];
const $ = id => document.getElementById(id);
const state = { route: 'none', business: null, lead: null };

function show(message, cls = '') { $('status').textContent = message; $('status').className = cls; }
function setConn(text, cls, title = '') { $('conn').textContent = text; $('conn').className = 'pill ' + cls; $('conn').title = title; }
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
function plural(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}`; }

async function checkConnection() {
  const status = await leaddockStatus();
  state.route = status.route;
  if (status.health) for (const k of Object.keys(LISTS)) if (Array.isArray(status.health[k])) LISTS[k] = status.health[k];
  const info = {
    helper: ['Ready', 'ok', 'Leads save straight into your LeadDock database. The desktop app does not need to be open.'],
    app: ['Connected', 'ok', 'Saving through the open LeadDock app. Run Start-LeadDock.bat once so leads also save while the app is closed.'],
    none: ['Saves offline', 'warn', status.needsKey
      ? 'The LeadDock app is open but this browser has no pairing key. Leads wait here until they can be delivered.'
      : 'LeadDock can\'t be reached yet, so leads wait in this browser and move into LeadDock automatically. Run Start-LeadDock.bat once on this PC to install the helper; after that the app never needs to be open.'],
  }[state.route];
  setConn(info[0], info[1], info[2]);
  $('routeInfo').textContent = info[2];
  if (state.route === 'none') $('settings').classList.remove('hidden');
}

async function refreshQueueNote(extra = '') {
  const queue = await leaddockQueue();
  const failed = queue.filter(i => i.error);
  const lines = [];
  if (extra) lines.push(extra);
  if (queue.length) lines.push(`${plural(queue.length, 'lead')} waiting in this browser — they move into LeadDock automatically once it can be reached.`);
  if (failed.length) lines.push('Could not deliver: ' + failed.map(i => `${i.business.name} (${i.error})`).join('; '));
  $('queueNote').textContent = lines.join('\n');
  $('queueNote').style.whiteSpace = 'pre-wrap';
  $('queueNote').classList.toggle('hidden', !lines.length);
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
    if (missing) input.placeholder = f === 'website' ? 'No website on this Google profile' : 'Not on the profile — type it if you know it';
  }
  $('f_maps_url').value = b.maps_url || '';
  $('mapsOpen').href = b.maps_url || '#';
  $('hoursBox').open = false;
  $('hoursBox').querySelector('summary').textContent = b.hours ? `Hours (${plural(b.hours.split('\n').length, 'day')})` : 'Hours (not listed)';

  const chips = [];
  const found = KEY_DETAILS.filter(f => b[f]).length;
  chips.push([`Found ${found} of ${KEY_DETAILS.length} key details`, found >= 5 ? 'good' : '']);
  if (!b.website) chips.push(['No website — hot lead', 'hot']);
  if (b.claimed === 'No') chips.push(['Unclaimed Google profile', 'hot']);
  if (/closed/i.test(b.business_status || '')) chips.push([b.business_status, 'bad']);
  const reviews = parseInt(String(b.review_count || '').replace(/\D/g, ''), 10);
  if (!isNaN(reviews) && reviews < 10) chips.push([`Only ${plural(reviews, 'review')}`, 'hot']);
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
  } else if (state.route !== 'none') {
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
  if (state.route !== 'none') {
    try {
      const r = await leaddockSend('lookup', { business: state.business });
      state.lead = r.found ? r.lead : null;
    } catch (e) {
      if (e.unavailable) await checkConnection();
      else show(e.message, 'error');
    }
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
  const business = collectBusiness();
  const crm = {
    status: $('c_status').value, priority: $('c_priority').value, next_followup: $('c_followup').value,
    note: $('c_note').value.trim(), note_type: $('c_note_type').value,
  };
  const done = async () => { $('c_note').value = ''; await chrome.storage.local.remove('draft'); };
  try {
    if (!business.name) throw new Error('Business name is required.');
    let r;
    try {
      r = await leaddockSend('capture', { business, crm });
    } catch (e) {
      if (!e.unavailable) throw e;
      // LeadDock can't be reached right now: keep the lead in the browser and deliver it automatically later.
      const waiting = await leaddockEnqueue(business, crm);
      await done();
      await checkConnection();
      await refreshQueueNote();
      show(`✓ Saved in this browser (${plural(waiting, 'lead')} waiting). It moves into LeadDock automatically — nothing else to do.`, 'ok');
      return;
    }
    state.business = business;
    state.lead = r.lead || null;
    await done();
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
  await chrome.storage.local.set({ pairingKey: $('key').value.trim() });
  await checkConnection();
  show(state.route === 'none' ? 'Key saved. LeadDock is still not reachable — leads will wait in this browser.' : 'Key saved.', state.route === 'none' ? 'error' : 'ok');
  if (state.route !== 'none') {
    const { sent } = await leaddockFlush();
    await refreshQueueNote(sent ? `✓ Delivered ${plural(sent, 'waiting lead')} to LeadDock.` : '');
    if (state.business) await refreshLookup();
  }
};
$('openApp').onclick = async () => {
  if (!state.lead) return;
  try {
    const r = await leaddockSend('open', { id: state.lead.id });
    show(r.opened === 'launched' ? 'Opening LeadDock…' : 'Showing it in LeadDock.', 'ok');
  } catch (e) { show(e.unavailable ? 'LeadDock is not reachable from the browser yet.' : e.message, 'error'); }
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
  const { pairingKey } = await chrome.storage.local.get(['pairingKey']);
  $('key').value = pairingKey || '';
  await checkConnection();
  let delivered = '';
  if (state.route !== 'none' && (await leaddockQueue()).length) {
    const { sent } = await leaddockFlush();
    if (sent) delivered = `✓ Delivered ${plural(sent, 'waiting lead')} to LeadDock.`;
  }
  await refreshQueueNote(delivered);
  await loadPage();
})();
