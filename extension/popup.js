async function check() {
  const el = document.getElementById("status");
  const ports = [8765, 8001];
  for (const port of ports) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/browser/tabs`);
      if (r.ok) {
        const j = await r.json();
        el.innerHTML = `<span class="ok">● Connected</span> · ${j.tabs.length} tabs synced · port ${port}`;
        return;
      }
    } catch {}
  }
  el.innerHTML = `<span class="bad">● Disconnected</span> · is Launchkey Mixer running?`;
}

check();
setInterval(check, 2000);
