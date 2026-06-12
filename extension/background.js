/**
 * Launchkey Mixer Tab Bridge — service worker
 * --------------------------------------------
 * Maintains a WebSocket connection to a local Launchkey Mixer instance
 * (`ws://127.0.0.1:8765/api/browser/ws` by default).
 *
 * Sends:    {"type": "tabs", "tabs": [...] }    on any tab update
 * Receives: {"type": "mute_tab", "selector": "tab:123" | "regex:youtube", "muted": true}
 *           {"type": "toggle_tab_mute", "selector": "..."}
 *           {"type": "focus_tab", "selector": "..."}
 *
 * Selector formats:
 *   - "tab:<id>"      -> exact tab id
 *   - "regex:<text>"  -> case-insensitive substring match on tab.title OR tab.url
 *   - anything else   -> treated as a regex pattern too
 */

const DEFAULT_PORTS = [8765, 8001];
const RECONNECT_MS = 3000;

let ws = null;
let reconnectTimer = null;
let currentPortIndex = 0;

function pickUrl() {
  const port = DEFAULT_PORTS[currentPortIndex % DEFAULT_PORTS.length];
  return `ws://127.0.0.1:${port}/api/browser/ws`;
}

async function fetchTabs() {
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

async function pushTabs() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  try {
    const tabs = await fetchTabs();
    ws.send(JSON.stringify({ type: "tabs", tabs }));
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
  const pattern = selector.startsWith("regex:") ? selector.slice(6) : selector;
  let re;
  try {
    re = new RegExp(pattern, "i");
  } catch {
    // Treat as plain substring on regex parse error
    const needle = pattern.toLowerCase();
    return allTabs.filter(
      (t) => (t.title || "").toLowerCase().includes(needle) || (t.url || "").toLowerCase().includes(needle),
    );
  }
  return allTabs.filter((t) => re.test(t.title || "") || re.test(t.url || ""));
}

async function handleCommand(msg) {
  const allTabs = await chrome.tabs.query({});
  switch (msg.type) {
    case "hello":
      console.log("[LK] connected:", msg.server);
      pushTabs();
      break;
    case "mute_tab": {
      const matches = findMatchingTabs(msg.selector, allTabs);
      for (const t of matches) {
        await chrome.tabs.update(t.id, { muted: !!msg.muted });
      }
      pushTabs();
      break;
    }
    case "toggle_tab_mute": {
      const matches = findMatchingTabs(msg.selector, allTabs);
      for (const t of matches) {
        const cur = t.mutedInfo && t.mutedInfo.muted;
        await chrome.tabs.update(t.id, { muted: !cur });
      }
      pushTabs();
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
    case "pong":
      break;
    default:
      console.warn("[LK] unknown command", msg);
  }
}

function connect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  const url = pickUrl();
  try {
    ws = new WebSocket(url);
  } catch (e) {
    console.warn("[LK] WS construct failed, retrying...", e);
    scheduleReconnect();
    return;
  }

  ws.addEventListener("open", () => {
    console.log("[LK] WS open ->", url);
    pushTabs();
  });
  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      handleCommand(msg);
    } catch (e) {
      console.warn("[LK] bad msg", e);
    }
  });
  ws.addEventListener("close", () => {
    console.log("[LK] WS closed; rotating port; reconnecting...");
    currentPortIndex += 1;
    scheduleReconnect();
  });
  ws.addEventListener("error", () => {
    // 'close' will fire next — schedule there
  });
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_MS);
}

// Push tab updates whenever they change
chrome.tabs.onCreated.addListener(pushTabs);
chrome.tabs.onUpdated.addListener(pushTabs);
chrome.tabs.onRemoved.addListener(pushTabs);
chrome.tabs.onActivated.addListener(pushTabs);

// Keep the service worker awake-ish by pinging every 25s
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: "ping" }));
    } catch {}
  }
}, 25000);

// Periodic resync (catches missed onAudibleChanged etc.)
setInterval(pushTabs, 5000);

connect();
