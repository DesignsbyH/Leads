const keyField = document.getElementById('key');
const status = document.getElementById('status');
const preview = document.getElementById('preview');
const button = document.getElementById('capture');
chrome.storage.local.get(['pairingKey'], x => { keyField.value = x.pairingKey || ''; });
document.getElementById('saveKey').onclick = async () => {
  await chrome.storage.local.set({ pairingKey: keyField.value.trim() });
  show('Pairing key saved.', 'okay');
};
function show(message, style = '') { status.textContent = message; status.className = style; }
function isBusinessUrl(url) {
  try { const u = new URL(url); return u.protocol === 'https:' && /^(www\.)?google\.[a-z.]+$/i.test(u.hostname) && u.pathname.includes('/maps/place/'); }
  catch { return false; }
}
// This function executes in the Google Maps tab. Keep it self-contained.
function grabBusiness() {
  const label = e => (e?.getAttribute('aria-label') || '').trim();
  const text = e => (e?.textContent || '').trim();
  const visible = e => !!(e && e.getClientRects().length);
  const main = document.querySelector('div[role="main"]') || document;
  const buttons = [...main.querySelectorAll('button,a,[data-item-id]')];
  const findLabel = re => buttons.find(e => visible(e) && re.test(label(e)));
  const getById = re => buttons.find(e => visible(e) && re.test(e.getAttribute('data-item-id') || ''));
  const addressEl = getById(/^address$/) || findLabel(/^Address\s*:/i);
  const phoneEl = getById(/^phone:tel/) || findLabel(/^(Phone|Call|Telephone)\s*:/i);
  const address = (label(addressEl) || text(addressEl)).replace(/^Address\s*:\s*/i, '').trim();
  const phoneRaw = (label(phoneEl) || text(phoneEl)).replace(/^(Phone|Call|Telephone)\s*:\s*/i, '');
  const phone = (phoneRaw.match(/\+?\d[\d().\s-]{7,}\d/) || [])[0] || '';
  let link = getById(/^authority$/) || findLabel(/^(Website|Site web)\s*:/i);
  let website = link?.href || link?.closest('a')?.href || '';
  if (website.includes('google.com/url?')) {
    try { website = new URL(website).searchParams.get('q') || website; } catch {}
  }
  const maps_url = location.href;
  // Google Maps can have a search results panel and an individual business panel
  // simultaneously; avoid treating a search result heading as the selected lead.
  let name = text(main.querySelector('h1'));
  if (!name || /^(results|search results)$/i.test(name)) {
    const encoded = decodeURIComponent((new URL(location.href).pathname.split('/maps/place/')[1] || '').split('/')[0] || '');
    name = encoded.replace(/\+/g, ' ').trim();
  }
  const category = text(main.querySelector('button[jsaction*="category"]'));
  const ratingLabel = label(main.querySelector('[role="img"][aria-label*="star"]'));
  const rating = (ratingLabel.match(/\d(?:[.,]\d)?/) || [])[0] || '';
  return { name, category, address, phone, website, maps_url, rating, review_count: '' };
}
async function currentTab() {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  return tab;
}
async function parseCurrent() {
  const tab = await currentTab();
  if (!tab || !isBusinessUrl(tab.url || '')) throw Error('Open an individual business in Google Maps first.');
  let data;
  try {
    const [result] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: grabBusiness});
    data = result?.result;
  } catch (e) {
    throw Error('Cannot read this tab. In Edge extension settings, allow access to google.com, then reload Maps. ' + e.message);
  }
  if (!data?.name) {
    const encoded = decodeURIComponent(new URL(tab.url).pathname.split('/maps/place/')[1].split('/')[0]);
    data = {...data, name: encoded.replace(/\+/g, ' ')};
  }
  if (!data?.name) throw Error('No business name detected. Reopen the business details panel.');
  data.maps_url = tab.url;
  return data;
}
async function refreshPreview() {
  button.disabled = true;
  try {
    const b = await parseCurrent();
    preview.textContent = `${b.name}\n${b.address || 'Address not detected — can edit later'}\n${b.phone || 'Phone not detected — can edit later'}\n${b.website || 'Website not detected — can edit later'}`;
    button.disabled = false;
    show('Business recognized. Ready to capture.', 'okay');
  } catch (e) { preview.textContent = e.message; show('Select a business profile in Google Maps.',''); }
}
button.onclick = async () => {
  button.disabled = true;
  show('Saving business…');
  try {
    const info = await parseCurrent();
    const key = keyField.value.trim();
    if (!key) throw Error('Enter the pairing key from the desktop app first.');
    await chrome.storage.local.set({pairingKey: key});
    const response = await fetch('http://127.0.0.1:18765/capture', {
      method: 'POST', headers: {'Content-Type':'application/json', 'X-LeadDock-Key':key},
      body: JSON.stringify(info), signal: AbortSignal.timeout(7000)
    });
    const body = await response.json();
    if (!response.ok) throw Error(body.error || `Capture failed (${response.status})`);
    show(`✓ ${body.name} ${body.result} in LeadDock.`, 'okay');
  } catch (e) { show('Could not capture: ' + e.message + '\nConfirm the desktop app is running.', 'error'); }
  finally { button.disabled = false; }
};
refreshPreview();
