/**
 * Launchkey Mixer Tab Bridge — service worker (MV3)
 * --------------------------------------------------
 * Maintains a WebSocket connection to a local Launchkey Mixer instance
 * (default `ws://127.0.0.1:8765/api/browser/ws`, falls back to :8001).
 *
 * MV3 service workers go idle after ~30s of inactivity, which breaks
 * long-lived WebSockets. Strategy: chrome.alarms (only reliable wake-up
 * mechanism in MV3) fires every 25s, reconnects WS if dead, and pushes a
 * fresh tab snapshot.
 *
 * Sends:    {"type":"tabs", "tabs":[...]}     after every tab event
 *           {"type":"ping"}                   keepalive
 * Receives: {"type":"mute_tab", "selector":"tab:123" | "regex:youtube", "muted":true}
 *           {"type":"toggle_tab_mute", "selector":"..."}
 *           {"type":"focus_tab", "selector":"..."}
 */

const PORTS = [8765, 8001];
let portIndex = 0;
let ws = null;
let connecting = false;

function wsUrl() {
  return `ws://127.0.0.1:${PORTS[portIndex % PORTS.length]}/api/browser/ws`;
}

async function snapshotTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs.map((t) => ({
    tabId: t.id,
    title: t.title || "",
    url: t.url || "",
    audible: !!t.audible,
    muted: !!(t.mutedInfo && t.mutedInfo.muted),
    windowId: t.windowId,
    favIconUrl: t.favIconUrl || "",
    active: !!t.active,
  }));
}

async function safeSend(payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  try {
    ws.send(JSON.stringify(payload));
    return true;
  } catch (e) {
    console.warn("[LK] send failed", e);
    return false;
  }
}

async function pushTabs() {
  try {
    const tabs = await snapshotTabs();
    await safeSend({ type: "tabs", tabs });
  } catch (e) {
    console.warn("[LK] pushTabs failed", e);
  }
}

function findMatchingTabs(selector, allTabs) {
  if (!selector) return [];
  if (selector.startsWith("tab:")) {
    const id = parseInt(selector.slice(4), 10);
    return allTabs.filter((t) => t.id === id);
  }
  const raw = selector.startsWith("regex:") ? selector.slice(6) : selector;
  let re;
  try { re = new RegExp(raw, "i"); } catch { re = null; }
  if (re) return allTabs.filter((t) => re.test(t.title || "") || re.test(t.url || ""));
  const needle = raw.toLowerCase();
  return allTabs.filter(
    (t) => (t.title || "").toLowerCase().includes(needle) || (t.url || "").toLowerCase().includes(needle),
  );
}

async function handleCommand(msg) {
  console.log("[LK] cmd:", msg);
  if (msg.type === "hello") {
    await pushTabs();
    return;
  }
  if (msg.type === "pong") return;

  const allTabs = await chrome.tabs.query({});
  switch (msg.type) {
    case "mute_tab": {
      for (const t of findMatchingTabs(msg.selector, allTabs)) {
        await chrome.tabs.update(t.id, { muted: !!msg.muted });
      }
      await pushTabs();
      break;
    }
    case "toggle_tab_mute": {
      for (const t of findMatchingTabs(msg.selector, allTabs)) {
        const cur = t.mutedInfo && t.mutedInfo.muted;
        await chrome.tabs.update(t.id, { muted: !cur });
      }
      await pushTabs();
      break;
    }
    case "focus_tab": {
      const matches = findMatchingTabs(msg.selector, allTabs);
      if (matches.length) {
        const t = matches[0];
        await chrome.windows.update(t.windowId, { focused: true });
        await chrome.tabs.update(t.id, { active: true });
      }
      break;
    }
    default:
      console.warn("[LK] unknown cmd", msg);
  }
}

function isAlive() {
  return ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING);
}

function connect() {
  if (connecting) return;
  if (isAlive()) return;
  connecting = true;
  const url = wsUrl();
  console.log("[LK] connecting", url);
  try {
    ws = new WebSocket(url);
  } catch (e) {
    console.warn("[LK] WS construct failed", e);
    connecting = false;
    portIndex += 1;
    return;
  }

  ws.addEventListener("open", () => {
    console.log("[LK] WS open", url);
    connecting = false;
    pushTabs();
  });
  ws.addEventListener("message", (ev) => {
    try { handleCommand(JSON.parse(ev.data)); }
    catch (e) { console.warn("[LK] bad msg", e); }
  });
  ws.addEventListener("close", () => {
    console.log("[LK] WS closed");
    connecting = false;
    ws = null;
    portIndex += 1;
  });
  ws.addEventListener("error", () => {
    // 'close' fires after — port rotation happens there
    connecting = false;
  });
}

// --- chrome.alarms is the MV3-correct way to schedule periodic work ---
// 0.25 min == 15s. (Minimum allowed for registered alarms is 30s on Chrome
// stable for unpacked extensions; tighter intervals get rounded up.)
chrome.alarms.create("keepalive", { periodInMinutes: 0.25 });
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "keepalive") return;
  if (!isAlive()) {
    connect();
    return;
  }
  await safeSend({ type: "ping" });
  await pushTabs();
});

// React immediately to tab events (within the SW's lifetime)
chrome.tabs.onCreated.addListener(pushTabs);
chrome.tabs.onUpdated.addListener(pushTabs);
chrome.tabs.onRemoved.addListener(pushTabs);
chrome.tabs.onActivated.addListener(pushTabs);

// Initial connect at install / SW boot
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();
