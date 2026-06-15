/**
 * Resolves a mapping into its live source state by looking it up in the
 * pycaw session list and / or browser-extension tab list.
 *
 *   sources.appFor("chrome.exe", sessions)
 *   sources.tabFor("tab:123", tabs)        // or "regex:youtube"
 *   sources.resolve(mapping, sessions, tabs)
 *
 * Returned shape is uniform so the UI doesn't care whether the source is a
 * desktop app or a browser tab:
 *   { kind: "app" | "tab" | null,
 *     label: string,
 *     icon: string | null,      // favicon URL for tabs
 *     volume: number (0..1),
 *     muted: boolean,
 *     audible: boolean }
 */

export const FOCUSED = "__focused__";

export function appFor(processName, sessions = []) {
  if (!processName) return null;
  const lc = processName.toLowerCase();
  return (
    sessions.find((s) => (s.process_name || "").toLowerCase() === lc) ||
    sessions.find((s) => (s.display_name || "").toLowerCase() === lc) ||
    null
  );
}

export function tabsFor(selector, tabs = []) {
  if (!selector || !tabs.length) return [];
  if (selector.startsWith("tab:")) {
    const id = parseInt(selector.slice(4), 10);
    return tabs.filter((t) => t.tabId === id);
  }
  const raw = selector.startsWith("regex:") ? selector.slice(6) : selector;
  try {
    const re = new RegExp(raw, "i");
    return tabs.filter((t) => re.test(t.title || "") || re.test(t.url || ""));
  } catch {
    const needle = raw.toLowerCase();
    return tabs.filter(
      (t) =>
        (t.title || "").toLowerCase().includes(needle) ||
        (t.url || "").toLowerCase().includes(needle),
    );
  }
}

export function resolve(mapping, sessions = [], tabs = []) {
  if (!mapping) return null;
  const action = mapping.action_type;
  const target = mapping.target_app;

  // Browser actions
  if (action && action.includes("tab")) {
    const matches = tabsFor(target, tabs);
    if (!matches.length) {
      return {
        kind: "tab",
        label: target || "tab",
        icon: null,
        volume: 0,
        muted: false,
        audible: false,
        missing: true,
      };
    }
    const t = matches[0];
    return {
      kind: "tab",
      label: t.title || t.url || `tab ${t.tabId}`,
      icon: t.favIconUrl || null,
      volume: 1,
      muted: !!t.muted,
      audible: !!t.audible,
    };
  }

  // System / focused / app actions
  if (target === FOCUSED) {
    return {
      kind: "focused",
      label: "Focused Window",
      icon: null,
      volume: 0,
      muted: false,
      audible: false,
    };
  }

  if (action === "system_volume" || !target) {
    return {
      kind: "system",
      label: action ? action.replace(/_/g, " ") : "—",
      icon: null,
      volume: 0,
      muted: false,
      audible: false,
    };
  }

  const session = appFor(target, sessions);
  if (session) {
    return {
      kind: "app",
      label: session.display_name || session.process_name,
      icon: null,
      volume: typeof session.volume === "number" ? session.volume : 0,
      muted: !!session.muted,
      audible: !session.muted && session.volume > 0,
    };
  }

  return {
    kind: "app",
    label: target,
    icon: null,
    volume: 0,
    muted: false,
    audible: false,
    missing: true,
  };
}
