# LeadDock — Local business prospecting CRM

A Windows desktop CRM plus a Microsoft Edge / Chrome extension. Open a business's Google profile (in Google Maps or Google Search), click the LeadDock icon, and the business is saved as a lead with its phone, website, address, hours, rating and more. **The desktop app does not need to be open** — a small helper that Edge starts on demand saves the lead straight into your LeadDock database. Then open the desktop app whenever you want to work your leads: log calls and notes, move them through your pipeline, and set follow-ups. Everything runs and is stored on your own PC (SQLite). No cloud account is needed.

## What's new in 2.7
- **Business types.** Every lead is filed under a broad type (Church & Religious, Construction & Remodeling, Plumbing, Roofing, HVAC, Restaurants & Food, Medical & Health…), worked out from Google's category. "Baptist church" and "Catholic church" both go under Church & Religious. You can change a lead's type anytime, in the popup or the app.
- **Filter sidebar** in the app: pick a business type, stage, city and view (Follow-ups due, Never contacted, No website…), and they combine. Every option shows how many leads it has.
- **Call sessions.** Filter to e.g. your church leads and click **📞 Call these**. LeadDock shows one lead at a time with a big phone number and a **Call** button. Click what happened (No answer, Left voicemail, Interested, Call back later, Sent proposal, Not interested, Wrong number), add a note, then **Save & next**. The call is logged, the stage moves and the follow-up date is set for you.
- **Faster note-taking and status changes:** one-click stage buttons, one-click call outcomes on every lead, editable timeline notes, and *Type* and *Last note* columns in the list.

## What was new in 2.6
- **Save leads with LeadDock closed.** The extension talks to a small LeadDock helper that Edge starts only when you save, so you no longer need the desktop app running. The desktop app installs the helper automatically the first time it starts.
- **Nothing gets lost.** If LeadDock can't be reached at all (e.g. before the helper is installed), the lead waits in the browser (the icon shows a number) and moves into LeadDock automatically later.
- **Open in LeadDock** in the popup starts the desktop app on that lead if it's closed.
- The popup shows the lead's **Google Maps link**, and says plainly when a business has **no website on its Google profile** (that's a hot lead, not a capture problem).
- Closing the desktop app window now simply quits it.

## What was new in 2.5
- **Capture fixed.** When you opened a business from a search results list, the extension read the *results list* instead of the business, so phone, website, address and category came back empty (and the rating could belong to a different business). It now finds the business panel.
- **More details per lead:** phone, website, full address split into city/state/ZIP, category, rating, review count, opening hours, plus code, map coordinates, open/closed status, unclaimed-profile flag, and Google's permanent place ID. The place ID means re-capturing a business always updates the same lead, even if the Maps link changes.
- **Google Search business profiles** (the panel on the right of search results) can be captured too.
- **Website scan:** LeadDock visits the business's own website to find an **email address** and **social media links**. It also flags problems you can pitch: **no website**, no HTTPS, not mobile-friendly, outdated copyright year, site down or broken, or a "website" that is only a Facebook page.
- **Work your leads from the popup:** reopening a business you already saved shows its stage, follow-up and recent activity. You can change the stage, set a follow-up or add a note right there.
- **Desktop CRM:** a notes & activity timeline (notes, calls, emails, texts, visits, meetings), quick stage/priority/follow-up controls, views such as *Follow-ups due*, *Never contacted*, *No website*, *Website issues* and *Unclaimed profiles*, sortable color-coded columns, right-click and bulk actions, and pipeline totals.

## Install on Windows (first time)
1. Install Python 3.10+ from python.org, enabling **Add Python to PATH** (or use the Windows `py` launcher).
2. Unzip the folder to `C:\LeadDock-2.0` (recommended). **Do not launch from inside the ZIP.**
3. Double-click **Start-LeadDock.bat**. It installs the desktop dependencies into `%LOCALAPPDATA%\LeadDock2\venv` so OneDrive/Desktop folder lengths do not break installs.
4. The first start also installs the **browser helper**. After that you can close LeadDock whenever you like; the extension still saves leads.
5. Open `edge://extensions` (Chrome: `chrome://extensions`), enable **Developer mode**, choose **Load unpacked**, and choose `C:\LeadDock-2.0\extension` (the inner extension folder).
6. Open a business in Google Maps and click the LeadDock icon (or press **Alt+Shift+L**). The pill at the top should say **Ready**.

## Updating
Your leads and notes are kept. The database is upgraded automatically the first time the new version starts.
1. Exit the running LeadDock (right-click the tray icon → **Exit LeadDock**, or close its window).
2. Update the files (`git pull`, or replace them) and double-click **Start-LeadDock.bat** once. This installs/refreshes the browser helper. You can close the app afterwards.
3. In `edge://extensions`, click **Remove** on the old LeadDock extension, then **Load unpacked** and pick the `extension` folder again. **Updating to 2.6 needs this remove-and-load step once** (the extension now has a fixed ID so the helper can trust it); for later updates **Reload (↻)** is enough.

## Capturing leads
The pill at the top of the popup shows how it saves: **Ready** (straight into LeadDock, app can be closed), **Connected** (through the open app), or **Saves offline** (the lead waits in the browser and is delivered automatically once LeadDock can be reached).

1. In Google Maps, search (e.g. "plumbers in Springfield IL") and **click a business** so its details panel opens. Or open a business's profile in Google Search.
2. Click the LeadDock icon (or press **Alt+Shift+L**). The popup shows what was found, ready to edit. Fields Google doesn't list are highlighted so you can type them in.
3. Optionally pick a stage, priority and follow-up date, and add a note, then click **Save lead**.
4. If the business is already in LeadDock, the popup says so and shows its stage and recent activity. **Update lead** refreshes the Google details without touching your notes, stage or contact info.

Flags in the popup point out hot prospects: **No website**, **Unclaimed Google profile**, **Only N reviews**, closed businesses.

A blank website means the business has no website on its Google profile. You can tell from Google itself: in the results list such businesses only have a **Directions** button (no **Website** button), and their profile shows **Add website**.

> If Google shows you a "limited view of Google Maps" (it does this for some signed-out visitors), it hides review counts and most opening hours. Sign in to Google in that browser for complete details.

## Working your leads in the desktop app
- **Filter sidebar (left):** *Show* (All leads · Follow-ups due · Never contacted · No website · Website issues · Unclaimed profiles · High priority · Open deals), *Business type*, *Stage* and *City*. Click one option in each to combine them, e.g. **Church & Religious + New + Springfield, IL**. The numbers show how many leads each option would give you. **✕ Clear filters** resets everything, and the search box narrows it further.
- **📞 Call these N:** starts a call session for the leads you're looking at (only those with a phone number). For each lead: click **Call** (opens Phone Link/Teams/your calling app) or dial it yourself, click what happened (or press Alt+1…Alt+7), add a note, then **Save & next** (Ctrl+Enter). Each outcome sets sensible defaults you can change before saving: *No answer* → follow up in 2 days, *Left voicemail* → 3 days, *Interested* → stage Follow Up and call tomorrow, *Call back later* → next week, *Sent proposal* → stage Proposal, *Not interested* / *Wrong number* → stage Lost. Stages never move backwards automatically. **Skip** leaves a lead untouched. To call a hand-picked set, select several leads, right-click and choose **Call these leads**.
- **Lead panel (right):** click a **stage button** to move the lead, pick its **business type**, priority and **follow-up** (quick picks or calendar). **📞 Call** dials the number.
- **Notes & activity:** the **Log a call** buttons record an outcome in one click (anything typed in the note box is added to it). Or choose Note, Call, Email, Text, Visit or Meeting, type what happened, and press **Add** (Ctrl+Enter). Logging contact records the *last contacted* date and moves a *New* or *Qualified* lead to *Contacted*. **Pinned notes** hold the always-visible summary. Fix or remove your own entries with **edit** / **✕** in the timeline.
- **Business info** tab: edit any field, including contact person and deal value. Everything saves automatically.
- **Website & social** tab: run a website scan and see the audit, the issues found and the social links.
- **Table:** columns include *Type* and *Last note* (your latest call or note). Click a column header to sort. Right-click a header to hide or show columns (Priority and Last contact are hidden at first). Right-click leads (Ctrl/Shift-click to select several) to set the stage, **business type**, priority or follow-up, log a call outcome, start a call session, scan websites, export or delete. Double-click a lead to start writing a note.
- **Pipeline** tab: leads and deal value per stage, open pipeline value and win rate. Double-click a stage to list its leads.
- **Export CSV** exports the leads currently shown (so you can export, say, just your church leads with no website). **Import CSV** understands common column names (Business Name, Phone Number, Zip Code, Stage…).
- On startup, LeadDock reminds you about follow-ups that are due.

## Website scan
When a captured lead has a website, LeadDock scans it in the background (leads saved while the app was closed are scanned the next time you open it). Turn this off in **More ▾ → Automatically scan websites of captured leads**. You can also scan from the lead panel, or with **More ▾ → Scan all websites not scanned yet**. The scan only visits that business's own site (homepage plus up to two contact/about pages). It fills in a blank email or phone, adds social links, and records issues: no HTTPS, not mobile-friendly, outdated ©, slow, broken, no meta description, or only a Facebook/Yelp page. Some sites block automated visits; those are marked "could not scan" rather than counted as broken.

## Data & privacy
- Data: `%LOCALAPPDATA%\LeadDock2\leads.sqlite3`. Pairing key: `%LOCALAPPDATA%\LeadDock2\capture_key.txt`. Settings: `settings.json` in the same folder. Use **More ▾ → Back up database…** regularly.
- The browser helper is registered for your Windows user only (`HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.designsbyh.leaddock`, plus the Chrome/Brave equivalents) and only the LeadDock extension is allowed to start it. Its files live in `%LOCALAPPDATA%\LeadDock2\native`.
- While the desktop app is open it also listens on `127.0.0.1:18765` (your PC only) as a fallback; that route requires the pairing key. Anyone with access to your Windows profile can read the local data; protect your account.

## Limitations
- The extension captures only the business you currently have open. It **does not bulk-scrape Google Maps**.
- Google changes its page layout often, so detection is best-effort. Check the popup preview and type in anything missing. For production-grade data, use Google's official Places API and follow Google Maps' terms and attribution rules.

## Troubleshooting
- **Popup says "Saves offline":** run **Start-LeadDock.bat** once so the helper gets installed, and make sure you removed and re-loaded the extension after updating (see *Updating*). Your saved leads are not lost; they're delivered automatically.
- **Still "Saves offline" on a work PC:** your IT policy may block browser helpers. Use the fallback: open LeadDock → **Connect browser**, copy the pairing key, paste it under ⚙ in the popup. Leads then save (and waiting ones are delivered) whenever the app is open.
- **"Key rejected":** copy the key again from **Connect browser** and paste it under ⚙ in the popup.
- **Website is blank:** check the business on Google Maps; if it has no **Website** button in the list (and shows **Add website** on its profile), it simply has no website listed.
- **Fields still missing after updating:** make sure you re-loaded the extension in `edge://extensions`, then reload the Google Maps tab. Click the business so its full details panel is open (not just highlighted in the list), then use **↻ Re-read page** in the popup.
- **Port already in use:** another LeadDock window is already open.
- **Dependencies fail:** update Python and rerun the batch file. To retry cleanly, exit LeadDock and delete `%LOCALAPPDATA%\LeadDock2\venv` **only**; never delete the database folder.

## For developers
Code layout: `leaddock/store.py` (database, merge rules), `leaddock/enrich.py` (website scanner), `leaddock/bridge.py` (extension requests + local HTTP API), `leaddock/native_host.py` (browser helper), `leaddock/app.py` (PySide6 UI), `extension/extractor.js` (reads the Google page), `extension/transport.js` (helper → app → offline queue), `extension/popup.*`, `extension/background.js` (delivers waiting leads).
Run the tests (standard library only) from the `LeadDock-2.0` folder: `python -m unittest discover -s tests`
