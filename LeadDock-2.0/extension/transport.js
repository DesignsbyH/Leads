// How the extension reaches LeadDock, shared by the popup and the background worker. In order of preference:
//  1. the LeadDock browser helper (native messaging): Edge starts it on demand, so the desktop app can be closed
//  2. the desktop app's local server (needs the pairing key), for setups where the helper isn't installed
//  3. neither available: the lead waits in the browser and is delivered automatically later
const LEADDOCK_HOST = 'com.designsbyh.leaddock';
const LEADDOCK_API = 'http://127.0.0.1:18765';

function unavailable(message, extra = {}) {
  return Object.assign(new Error(message), { unavailable: true }, extra);
}

async function leaddockNative(message) {
  let reply;
  try {
    reply = await chrome.runtime.sendNativeMessage(LEADDOCK_HOST, message);
  } catch (e) {
    throw unavailable('The LeadDock helper is not installed yet. Run Start-LeadDock.bat once.', { detail: e.message });
  }
  if (!reply) throw unavailable('The LeadDock helper did not answer.');
  if (reply.ok === false) throw new Error(reply.error || 'LeadDock could not do that.');
  return reply;
}

async function leaddockHttp(action, body) {
  const { pairingKey } = await chrome.storage.local.get(['pairingKey']);
  if (!pairingKey) throw unavailable('LeadDock is not reachable.');
  let res;
  try {
    res = await fetch(`${LEADDOCK_API}/${action}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-LeadDock-Key': pairingKey },
      body: JSON.stringify(body), signal: AbortSignal.timeout(8000),
    });
  } catch (e) {
    throw unavailable('The LeadDock desktop app is not running.');
  }
  let data = {};
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (res.status === 403) throw unavailable(data.error || 'Pairing key rejected.', { keyRejected: true });
  if (!res.ok) throw new Error(data.error || `LeadDock returned an error (${res.status})`);
  return data;
}

// Which route works right now: {route: 'helper' | 'app' | 'none', health}
async function leaddockStatus() {
  try { return { route: 'helper', health: await leaddockNative({ action: 'ping' }) }; } catch (e) { /* try the app */ }
  try {
    const res = await fetch(`${LEADDOCK_API}/health`, { signal: AbortSignal.timeout(2000) });
    const health = await res.json();
    const { pairingKey } = await chrome.storage.local.get(['pairingKey']);
    return { route: pairingKey ? 'app' : 'none', health, needsKey: !pairingKey };
  } catch (e) { /* nothing reachable */ }
  return { route: 'none' };
}

// One request over the best available route. Throws an error with .unavailable when LeadDock can't be reached.
async function leaddockSend(action, body) {
  try {
    return await leaddockNative({ action, ...body });
  } catch (e) {
    if (!e.unavailable) throw e;
  }
  return leaddockHttp(action === 'open' ? 'focus' : action, body);
}

// ---------------------------------------------------------------- leads waiting for delivery
async function leaddockQueue() {
  const { queue } = await chrome.storage.local.get(['queue']);
  return Array.isArray(queue) ? queue : [];
}

async function leaddockBadge() {
  const n = (await leaddockQueue()).length;
  await chrome.action.setBadgeText({ text: n ? String(n) : '' });
  if (n) await chrome.action.setBadgeBackgroundColor({ color: '#d98e04' });
}

async function leaddockEnqueue(business, crm) {
  return navigator.locks.request('leaddock-queue', async () => {
    const queue = await leaddockQueue();
    queue.push({ business, crm, queued_at: new Date().toISOString() });
    await chrome.storage.local.set({ queue });
    await leaddockBadge();
    return queue.length;
  });
}

// Deliver waiting leads. Returns {sent, left}. The lock stops the popup and background worker sending twice.
async function leaddockFlush() {
  return navigator.locks.request('leaddock-queue', async () => {
    const queue = await leaddockQueue();
    let sent = 0, stopped = false;
    const left = [];
    for (const item of queue) {
      if (stopped) { left.push(item); continue; } // LeadDock went away; keep the rest, in order
      try {
        await leaddockSend('capture', { business: item.business, crm: item.crm });
        sent++;
      } catch (e) {
        stopped = !!e.unavailable;
        left.push(stopped ? item : { ...item, error: e.message });
      }
    }
    if (queue.length) await chrome.storage.local.set({ queue: left });
    await leaddockBadge();
    return { sent, left: left.length, errors: left.filter(i => i.error).map(i => `${i.business.name}: ${i.error}`) };
  });
}
