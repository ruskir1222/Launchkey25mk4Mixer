# 🌐 Launchkey Mixer — Tab Bridge Extension

A tiny browser extension that lets the Launchkey Mixer dashboard list, mute, unmute and focus browser tabs from your Launchkey Mini MK4 25.

Works with **all Chromium browsers**: Chrome, Edge, Opera, Brave, Vivaldi, Arc.

---

## Install (developer mode)

1. Open your browser's extensions page:
   - **Chrome**:  `chrome://extensions`
   - **Edge**:    `edge://extensions`
   - **Opera**:   `opera://extensions`
   - **Brave**:   `brave://extensions`
2. Toggle **Developer mode** ON (top-right)
3. Click **Load unpacked**
4. Pick the `extension/` folder from this repo
5. You should see the **Launchkey Mixer Tab Bridge** icon appear

That's it. The extension auto-connects to your running Launchkey Mixer (either offline `.exe` or the cloud dashboard) over a local WebSocket and starts syncing tab info.

## How it talks to the app

- Extension → WebSocket → `ws://127.0.0.1:8765/api/browser/ws` (offline app)
- Falls back to `ws://127.0.0.1:8001/api/browser/ws` (local dev backend)
- All traffic is loopback only — no external requests.

## Privacy

The extension only reads:
- Tab IDs, titles, URLs (so you can pick which to mute)
- Audible / muted state

It sends these to **`127.0.0.1` only**. No cloud, no analytics. Open `background.js` to verify.

## Mapping a pad to mute a tab

In the Launchkey Mixer dashboard:
1. Click a pad → choose action **"Mute Browser Tab"** (or "Toggle Tab Mute")
2. Target: pick a tab from the live list, or type a substring (e.g. `youtube`) to always match by URL/title
3. Save — done. Tap the pad to mute that tab.

## Build / publish (future)

To publish on the Chrome Web Store:
```bash
cd extension
zip -r ../launchkey-tab-bridge.zip . -x "*.md"
```
Then upload via https://chrome.google.com/webstore/devconsole (one-time $5 fee for the developer account).
