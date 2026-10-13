# LeadDock 2.0 — Local business prospecting CRM

A Windows desktop CRM and Microsoft Edge extension for manually capturing the currently opened Google Maps business. Runs locally, stores leads in SQLite, and does not require cloud accounts.

## Install on Windows
1. Install Python 3.10+ from python.org, enabling **Add Python to PATH** (or use the Windows `py` launcher).
2. Unzip the folder to `C:\LeadDock-2.0` (recommended). **Do not launch from inside the ZIP.**
3. Double-click **Start-LeadDock.bat**. The script installs the desktop dependencies into `%LOCALAPPDATA%\LeadDock2\venv` so OneDrive/Desktop folder lengths do not break installs.
4. Keep LeadDock running. Closing the window hides it to the system tray; use **Exit LeadDock** in the tray menu to quit.
5. Click **Connect Edge** in LeadDock. Copy the pairing key shown.
6. Open `edge://extensions`, enable **Developer mode**, choose **Load unpacked**, and choose `C:\LeadDock-2.0\extension` (the inner extension folder).
7. Click the LeadDock extension icon in Edge, paste the pairing key, click **Save key**.
8. Go to Google Maps, click an individual business so its details panel opens, and click the extension icon → **Capture business**.

If you use Chrome instead of Edge, the unpacked extension also works with `chrome://extensions`.

## What gets captured
- Name, phone, street address, website, rating, number of reviews, category, and the Google Maps URL **when exposed by the currently visible Google Maps profile**.
- Google Maps frequently changes its HTML structure. Fields not visible or available to the extension will be left blank, and can be edited immediately in the CRM. Capture previews the detected values before saving.
- The app matches exact Google Maps URLs or business name + phone/address before creating a new record. Recapturing usually updates the existing record without erasing sales notes or stages.

## Desktop features
- Search across businesses, contacts and locations; filter by stage and high priority.
- Fully editable autosaving business details, notes, contact person, follow-up date, priority and deal value.
- Pipeline summary, CSV import/export, database backups, open Maps/website, phone copy, and tray operation.
- Data stored at `%LOCALAPPDATA%\LeadDock2\leads.sqlite3`, pairing secret stored at `%LOCALAPPDATA%\LeadDock2\capture_key.txt`.
- HTTP bridge listens **only** on `127.0.0.1:18765` and requires a random pairing key for saves. Anyone with access to the Windows profile can access local app data; protect your account.

## Limitations
- The Edge extension captures only the currently opened business. It **does not bulk-scrape Google Maps** or bypass access controls.
- Google Maps is a changing third-party UI, so field detection is best-effort, not guaranteed. Prefer authorized Google Places APIs for production-grade business data and comply with applicable Google Maps terms, attribution and data-storage requirements.
- No automatic background crawling, website scanning, email finding, or external enrichment has been implemented.
- This is a new 2.0 implementation, **not** a direct upgrade or migration of the original 1.0 database. To migrate, use 1.0 CSV export where available, then use **Import CSV** in 2.0.

## Troubleshooting
- `Failed to fetch`: ensure LeadDock desktop is running and the pairing key matches.
- `Port already in use`: exit other LeadDock 2.0 sessions from the system tray.
- Missing captured fields: inspect the capture preview. Try opening the full business panel, not just a search result. Enter missing fields manually.
- If dependencies fail: update Python and rerun the batch file. The venv is intentionally outside OneDrive. To retry cleanly, exit LeadDock and delete `%LOCALAPPDATA%\LeadDock2\venv` **only**; do not delete the database directory.
