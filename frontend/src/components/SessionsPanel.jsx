import { LK } from "@/constants/testIds";
import { Volume2, VolumeX, AudioLines } from "lucide-react";

export default function SessionsPanel({ sessions, helperConnected }) {
  return (
    <div data-testid={LK.sessionsPanel} className="surface p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="overline">live audio sessions</div>
        <AudioLines className="w-3.5 h-3.5 text-neutral-500" />
      </div>

      {!helperConnected && (
        <div className="text-xs text-neutral-500 font-mono py-6 text-center">
          waiting for helper agent…
        </div>
      )}

      {helperConnected && sessions.length === 0 && (
        <div className="text-xs text-neutral-500 font-mono py-6 text-center">
          no audio sessions active
        </div>
      )}

      <ul className="space-y-2 max-h-[420px] overflow-y-auto">
        {sessions.map((s, i) => {
          const pct = Math.round((s.volume || 0) * 100);
          return (
            <li
              key={s.process_name + i}
              data-testid={LK.sessionItem(s.process_name)}
              className="surface-hover p-2.5 rounded-sm bg-[#0e0e0e] border border-[#1f1f1f]"
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5 min-w-0">
                  {s.muted ? (
                    <VolumeX className="w-3 h-3 text-danger flex-none" />
                  ) : (
                    <Volume2 className="w-3 h-3 text-neutral-400 flex-none" />
                  )}
                  <span className="text-xs font-mono truncate" title={s.process_name}>
                    {s.display_name || s.process_name}
                  </span>
                </div>
                <span className="text-[10px] font-mono text-neutral-500">{pct}%</span>
              </div>
              <div className="meter-bar">
                <div className="meter-fill" style={{ width: `${pct}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
