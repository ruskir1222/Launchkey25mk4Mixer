/**
 * SourcesMixerPanel
 * -----------------
 * Unified mixer view combining:
 *   1. Windows audio sessions (from pycaw via the helper)
 *   2. Browser tabs (from the Tab Bridge extension via WebSocket)
 *
 * For each source we show:
 *   - icon / favicon
 *   - name / tab title
 *   - live volume meter (apps only — pycaw gives us per-app dB; browser
 *     mute is binary so we just show muted/audible)
 *   - mute indicator
 *   - "▣ E1, Pad 3" — which physical controls are mapped to this source
 */

import { LK } from "@/constants/testIds";
import { Volume2, VolumeX, Headphones, Globe } from "lucide-react";

// Pretty labels for control_id values (knob-1 -> "E1", pad-5 -> "Pad 5")
function prettyControl(id) {
  if (!id) return id;
  if (id.startsWith("knob-")) return `E${id.slice(5)}`;
  if (id.startsWith("pad-")) return `Pad ${id.slice(4)}`;
  if (id.startsWith("key-")) return `Key ${id.slice(4)}`;
  return id;
}

function mappingsForApp(processName, mappings = []) {
  const lc = (processName || "").toLowerCase();
  return mappings.filter(
    (m) => (m.target_app || "").toLowerCase() === lc && !m.action_type?.includes("tab"),
  );
}

function mappingsForTab(tab, mappings = []) {
  const tabSel = `tab:${tab.tabId}`;
  return mappings.filter((m) => {
    if (!m.action_type?.includes("tab")) return false;
    const t = m.target_app || "";
    if (t === tabSel) return true;
    const raw = t.startsWith("regex:") ? t.slice(6) : t;
    try {
      const re = new RegExp(raw, "i");
      return re.test(tab.title || "") || re.test(tab.url || "");
    } catch {
      const needle = raw.toLowerCase();
      return (
        (tab.title || "").toLowerCase().includes(needle) ||
        (tab.url || "").toLowerCase().includes(needle)
      );
    }
  });
}

function BoundChip({ controlIds }) {
  if (!controlIds.length) {
    return <span className="text-[9px] font-mono text-neutral-700">unmapped</span>;
  }
  return (
    <span className="text-[9px] font-mono text-brand truncate">
      ▣ {controlIds.map(prettyControl).join(", ")}
    </span>
  );
}

function AppRow({ session, mappings }) {
  const pct = Math.round((session.volume || 0) * 100);
  const muted = session.muted;
  const audible = !muted && pct > 0;
  const controls = mappings.map((m) => m.control_id);
  return (
    <li
      data-testid={LK.sessionItem(session.process_name)}
      className="p-2.5 rounded-sm bg-[#0e0e0e] border border-[#1f1f1f] hover:border-[#2a2a2a] transition-colors"
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-1.5 min-w-0">
          {muted ? (
            <VolumeX className="w-3 h-3 text-danger flex-none" />
          ) : audible ? (
            <Volume2 className="w-3 h-3 text-brand flex-none" />
          ) : (
            <Volume2 className="w-3 h-3 text-neutral-500 flex-none" />
          )}
          <span
            className="text-xs font-mono truncate"
            title={session.process_name}
          >
            {session.display_name || session.process_name}
          </span>
        </div>
        <span className="text-[10px] font-mono text-neutral-400 flex-none">{pct}%</span>
      </div>
      <div className="meter-bar mb-1">
        <div
          className={`meter-fill ${muted ? "opacity-30" : ""}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <BoundChip controlIds={controls} />
    </li>
  );
}

function TabRow({ tab, mappings }) {
  const muted = tab.muted;
  const audible = tab.audible && !muted;
  const controls = mappings.map((m) => m.control_id);
  return (
    <li
      className="p-2.5 rounded-sm bg-[#0e0e0e] border border-[#1f1f1f] hover:border-[#2a2a2a] transition-colors"
      title={tab.url}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-1.5 min-w-0">
          {muted ? (
            <VolumeX className="w-3 h-3 text-danger flex-none" />
          ) : audible ? (
            <Volume2 className="w-3 h-3 text-brand flex-none" />
          ) : (
            <Volume2 className="w-3 h-3 text-neutral-600 flex-none" />
          )}
          {tab.favIconUrl ? (
            <img
              src={tab.favIconUrl}
              alt=""
              className="w-3 h-3 rounded-sm flex-none"
              onError={(e) => (e.target.style.display = "none")}
            />
          ) : (
            <Globe className="w-3 h-3 text-neutral-500 flex-none" />
          )}
          <span className="text-xs font-mono truncate" title={tab.title}>
            {tab.title || tab.url || `tab ${tab.tabId}`}
          </span>
        </div>
        {audible && (
          <span className="text-[9px] font-mono text-brand uppercase tracking-wider flex-none">
            ● live
          </span>
        )}
      </div>
      <BoundChip controlIds={controls} />
    </li>
  );
}

export default function SourcesMixerPanel({
  sessions = [],
  browserTabs = [],
  mappings = [],
  helperConnected,
  browserConnected,
}) {
  const audibleApps = sessions.filter((s) => !s.muted).length;
  const audibleTabs = browserTabs.filter((t) => t.audible && !t.muted).length;

  return (
    <div data-testid={LK.sessionsPanel} className="space-y-4">
      {/* Desktop apps section */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            <Headphones className="w-3 h-3 text-neutral-500" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400">
              Desktop apps
            </span>
            {helperConnected && (
              <span className="text-[10px] font-mono text-neutral-600">
                · {sessions.length} session{sessions.length === 1 ? "" : "s"}
                {audibleApps > 0 && (
                  <span className="text-brand ml-1">· {audibleApps} live</span>
                )}
              </span>
            )}
          </div>
        </div>
        {!helperConnected ? (
          <div className="text-xs text-neutral-500 font-mono py-3 text-center bg-[#0c0c0c] rounded-sm border border-[#1a1a1a]">
            waiting for helper agent…
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-xs text-neutral-500 font-mono py-3 text-center bg-[#0c0c0c] rounded-sm border border-[#1a1a1a]">
            no audio sessions active
          </div>
        ) : (
          <ul className="space-y-1.5 max-h-[260px] overflow-y-auto pr-1">
            {sessions.map((s, i) => (
              <AppRow
                key={s.process_name + i}
                session={s}
                mappings={mappingsForApp(s.process_name, mappings)}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Browser tabs section */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5">
            <Globe className="w-3 h-3 text-neutral-500" />
            <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400">
              Browser tabs
            </span>
            {browserConnected && (
              <span className="text-[10px] font-mono text-neutral-600">
                · {browserTabs.length} tab{browserTabs.length === 1 ? "" : "s"}
                {audibleTabs > 0 && (
                  <span className="text-brand ml-1">· {audibleTabs} playing</span>
                )}
              </span>
            )}
          </div>
        </div>
        {!browserConnected ? (
          <div className="text-xs text-neutral-500 font-mono py-3 text-center bg-[#0c0c0c] rounded-sm border border-[#1a1a1a]">
            install the Tab Bridge extension to control tabs
          </div>
        ) : browserTabs.length === 0 ? (
          <div className="text-xs text-neutral-500 font-mono py-3 text-center bg-[#0c0c0c] rounded-sm border border-[#1a1a1a]">
            no tabs reported
          </div>
        ) : (
          <ul className="space-y-1.5 max-h-[260px] overflow-y-auto pr-1">
            {browserTabs
              .slice()
              .sort((a, b) => {
                // Audible tabs to the top
                const ab = (b.audible ? 1 : 0) - (a.audible ? 1 : 0);
                if (ab !== 0) return ab;
                return (b.muted ? 1 : 0) - (a.muted ? 1 : 0);
              })
              .map((t) => (
                <TabRow
                  key={t.tabId}
                  tab={t}
                  mappings={mappingsForTab(t, mappings)}
                />
              ))}
          </ul>
        )}
      </div>
    </div>
  );
}
