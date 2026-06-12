import { useMemo } from "react";
import { Settings2, Trash2 } from "lucide-react";

function controlLabel(id) {
  if (id.startsWith("knob-")) return `Knob ${id.split('-')[1]}`;
  if (id.startsWith("pad-")) return `Pad ${id.split('-')[1]}`;
  if (id.startsWith("key-")) return `Key ${id.split('-')[1]}`;
  if (id.startsWith("transport-")) return `Transport · ${id.split('-')[1]}`;
  if (id.startsWith("cc-ch")) {
    const m = id.match(/cc-ch(\d+)-(\d+)/);
    return m ? `CC #${m[2]} (ch ${m[1]})` : id;
  }
  if (id.startsWith("note-ch")) {
    const m = id.match(/note-ch(\d+)-(\d+)/);
    return m ? `Note ${m[2]} (ch ${m[1]})` : id;
  }
  return id.replace(/-/g, ' ');
}

export default function MappingsList({ mappings, onEdit, onDelete }) {
  const sorted = useMemo(() => {
    return [...mappings].sort((a, b) => a.control_id.localeCompare(b.control_id));
  }, [mappings]);

  if (sorted.length === 0) {
    return (
      <div data-testid="mappings-list" className="surface p-4">
        <div className="overline mb-2">active mappings</div>
        <div className="text-xs text-neutral-500 font-mono py-3 text-center">
          no mappings yet — click any control above or hit MIDI LEARN
        </div>
      </div>
    );
  }

  return (
    <div data-testid="mappings-list" className="surface p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="overline">active mappings</div>
        <span className="text-[10px] font-mono text-neutral-600">{sorted.length} bound</span>
      </div>
      <ul className="space-y-1 max-h-72 overflow-y-auto">
        {sorted.map((m) => (
          <li
            key={m.id}
            data-testid={`mapping-row-${m.control_id}`}
            className="group flex items-center justify-between p-2 rounded-sm bg-[#0e0e0e] border border-[#1f1f1f] hover:bg-[#151515]"
          >
            <button
              onClick={() => onEdit(m.control_id)}
              className="flex-1 text-left min-w-0 flex items-center gap-2"
            >
              <Settings2 className="w-3 h-3 text-brand flex-none" />
              <div className="min-w-0">
                <div className="text-xs font-mono text-white truncate">
                  {m.label || controlLabel(m.control_id)}
                </div>
                <div className="text-[10px] font-mono text-neutral-500 truncate">
                  {m.action_type}{m.target_app ? ` → ${m.target_app}` : ''}
                </div>
              </div>
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(m.control_id); }}
              className="opacity-0 group-hover:opacity-100 text-neutral-500 hover:text-danger transition-opacity p-1"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
