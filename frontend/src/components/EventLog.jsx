import { useEffect, useRef } from "react";
import { LK } from "@/constants/testIds";

export default function EventLog({ events }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events]);

  return (
    <div data-testid={LK.eventLog} ref={ref} className="max-h-44 overflow-y-auto font-mono text-[11px] space-y-0.5">
      {events.length === 0 ? (
        <div className="text-neutral-600">// waiting for MIDI activity from helper…</div>
      ) : (
        events.slice(-50).map((e, i) => (
          <div key={i} className="animate-slideUp flex gap-3 text-neutral-400">
            <span className="text-neutral-600">{e.timestamp.slice(11, 19)}</span>
            <span className="text-brand w-28 truncate">{e.control_id}</span>
            <span className="text-neutral-500 w-20">{e.raw_type}</span>
            <span className="text-neutral-300">value={e.value}</span>
          </div>
        ))
      )}
    </div>
  );
}
