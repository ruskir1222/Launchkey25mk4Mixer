async function check() {
  const el = document.getElementById("status");
  const tabsEl = document.getElementById("tabs");
  const ports = [8765, 8001];
  for (const port of ports) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/browser/tabs`);
      if (!r.ok) continue;
      const j = await r.json();
      if (j.connected) {
        el.innerHTML = `<span class="ok">● WebSocket connected</span> · ${j.tabs.length} tabs synced · port ${port}`;
      } else {
        el.innerHTML = `<span class="warn">● Server reachable but extension not connected via WebSocket</span> · port ${port}. <button id="reload">Reload extension</button>`;
        const btn = document.getElementById("reload");
        if (btn) btn.onclick = () => chrome.runtime.reload();
      }
      tabsEl.innerHTML = (j.tabs || []).slice(0, 6).map((t) => {
        const ico = t.muted ? "🔇" : t.audible ? "🔊" : "⚪";
        return `<div class="tab">${ico} ${escapeHtml((t.title || t.url || "").slice(0, 50))}</div>`;
      }).join("");
      return;
    } catch {}
  }
  el.innerHTML = `<span class="bad">● Cannot reach server</span> · is Launchkey Mixer running?`;
  tabsEl.innerHTML = "";
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

check();
setInterval(check, 2000);
