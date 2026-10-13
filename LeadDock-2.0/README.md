# LeadDock — Local business prospecting CRM

A Windows desktop CRM plus a Microsoft Edge / Chrome extension. Open a business's Google profile (in Google Maps or Google Search), click the LeadDock icon, and the business is saved as a lead with its phone, website, address, hours, rating and more. Then work your leads in the desktop app: log calls and notes, move them through your pipeline, and set follow-ups. Everything runs and is stored on your own PC (SQLite). No cloud account is needed.

## What's new in 2.5
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
4. Keep LeadDock running. Closing the window hides it to the system tray so the browser can keep sending leads. Use **More ▾ → Exit LeadDock** (or the tray menu) to quit.
5. Click **Connect browser** in LeadDock and copy the pairing key.
6. Open `edge://extensions` (Chrome: `chrome://extensions`), enable **Developer mode**, choose **Load unpacked**, and choose `C:\LeadDock-2.0\extension` (the inner extension folder).
7. Click the LeadDock extension icon (or press **Alt+Shift+L**), click **⚙**, paste the pairing key, click **Save key**.

## Updating from LeadDock 2.0
Your leads, notes and pairing key are kept. The database is upgraded automatically the first time the new version starts.
1. Exit the running LeadDock from the system tray (right-click the tray icon → **Exit LeadDock**).
2. Replace the files in your `LeadDock-2.0` folder with the new ones and double-click **Start-LeadDock.bat**.
3. In `edge://extensions`, click **Reload (↻)** on the LeadDock extension. **This step is required.** Without it Edge keeps using the old capture code.

## Capturing leads
1. In Google Maps, search (e.g. "plumbers in Springfield IL") and **click a business** so its details panel opens. Or open a business's profile in Google Search.
2. Click the LeadDock icon (or press **Alt+Shift+L**). The popup shows what was found, ready to edit. Fields Google doesn't list are highlighted so you can type them in.
3. Optionally pick a stage, priority and follow-up date, and add a note, then click **Save lead**.
4. If the business is already in LeadDock, the popup says so and shows its stage and recent activity. **Update lead** refreshes the Google details without touching your notes, stage or contact info.

Flags in the popup point out hot prospects: **No website**, **Unclaimed Google profile**, **Only N reviews**, closed businesses.

> If Google shows you a "limited view of Google Maps" (it does this for some signed-out visitors), it hides review counts and most opening hours. Sign in to Google in that browser for complete details.

## Working your leads in the desktop app
- **Views** (dropdown next to search): All leads · Follow-ups due · Never contacted · No website · Website issues · Unclaimed profiles · High priority · Open deals. Each view shows its count.
- **Stage / Priority / Follow-up** sit at the top of the lead panel. Follow-up has quick picks (Tomorrow, Next week…) and a calendar. Changes are logged in the timeline.
- **Notes & activity:** choose Note, Call, Email, Text, Visit or Meeting, type what happened, and press **Add** (Ctrl+Enter). Logging a call/email/text/visit/meeting records the *last contacted* date and moves a *New* or *Qualified* lead to *Contacted*. **Pinned notes** hold the always-visible summary. Delete your own entries with the ✕ in the timeline.
- **Business info** tab: edit any field, including contact person and deal value. Everything saves automatically.
- **Website & social** tab: run a website scan and see the audit, the issues found and the social links.
- **Table:** click a column header to sort. Right-click a header to hide or show columns. Right-click leads (Ctrl/Shift-click to select several) to set the stage, priority or follow-up, log a call, scan websites, export or delete. Double-click a lead to start writing a note.
- **Pipeline** tab: leads and deal value per stage, open pipeline value and win rate. Double-click a stage to list its leads.
- **Export CSV** exports the leads currently shown (so you can export just the "No website" view, for example). **Import CSV** understands common column names (Business Name, Phone Number, Zip Code, Stage…).
- On startup, LeadDock reminds you about follow-ups that are due.

## Website scan
When a captured lead has a website, LeadDock scans it in the background. Turn this off in **More ▾ → Automatically scan websites of captured leads**. You can also scan from the lead panel, or with **More ▾ → Scan all websites not scanned yet**. The scan only visits that business's own site (homepage plus up to two contact/about pages). It fills in a blank email or phone, adds social links, and records issues: no HTTPS, not mobile-friendly, outdated ©, slow, broken, no meta description, or only a Facebook/Yelp page. Some sites block automated visits; those are marked "could not scan" rather than counted as broken.

## Data & privacy
- Data: `%LOCALAPPDATA%\LeadDock2\leads.sqlite3`. Pairing key: `%LOCALAPPDATA%\LeadDock2\capture_key.txt`. Settings: `settings.json` in the same folder. Use **More ▾ → Back up database…** regularly.
- The browser bridge listens **only** on `127.0.0.1:18765` and requires the pairing key for every request. Anyone with access to your Windows profile can read the local data; protect your account.

## Limitations
- The extension captures only the business you currently have open. It **does not bulk-scrape Google Maps**.
- Google changes its page layout often, so detection is best-effort. Check the popup preview and type in anything missing. For production-grade data, use Google's official Places API and follow Google Maps' terms and attribution rules.

## Troubleshooting
- **Popup says "Desktop app offline":** start LeadDock (Start-LeadDock.bat) or open it from the tray.
- **"Key rejected":** copy the key again from **Connect browser** and paste it under ⚙ in the popup.
- **"Restart LeadDock app":** the desktop app is still the old version. Exit it from the tray and start it again.
- **Fields still missing after updating:** make sure you clicked **Reload** on the extension in `edge://extensions`, then reload the Google Maps tab. Click the business so its full details panel is open (not just highlighted in the list), then use **↻ Re-read page** in the popup.
- **Port already in use:** another LeadDock is already running. Check the system tray.
- **Dependencies fail:** update Python and rerun the batch file. To retry cleanly, exit LeadDock and delete `%LOCALAPPDATA%\LeadDock2\venv` **only**; never delete the database folder.

## For developers
Code layout: `leaddock/store.py` (database, merge rules), `leaddock/enrich.py` (website scanner), `leaddock/bridge.py` (local HTTP API), `leaddock/app.py` (PySide6 UI), `extension/extractor.js` (reads the Google page), `extension/popup.*`.
Run the tests (standard library only) from the `LeadDock-2.0` folder: `python -m unittest discover -s tests`
