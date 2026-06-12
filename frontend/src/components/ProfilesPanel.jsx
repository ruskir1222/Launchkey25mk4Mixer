import { useState } from "react";
import { LK } from "@/constants/testIds";
import { Plus, Trash2, Check } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function ProfilesPanel({ profiles, activeProfile, onActivate, onCreate, onDelete }) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const handleSave = async () => {
    if (!name.trim()) return;
    await onCreate(name.trim());
    setName("");
    setCreating(false);
  };

  return (
    <div className="surface p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="overline">macro profiles</div>
        <Button
          data-testid={LK.newProfileBtn}
          onClick={() => setCreating(v => !v)}
          variant="ghost" size="sm"
          className="h-6 w-6 p-0 rounded-sm hover:bg-[#1a1a1a]"
        >
          <Plus className="w-3.5 h-3.5" />
        </Button>
      </div>

      {creating && (
        <div className="mb-3 flex gap-2">
          <Input
            data-testid={LK.newProfileInput}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Profile name…"
            className="h-8 text-xs bg-[#0e0e0e] border-[#262626] rounded-sm font-mono"
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            autoFocus
          />
          <Button
            data-testid={LK.newProfileSave}
            onClick={handleSave}
            size="sm"
            className="h-8 rounded-sm bg-brand hover:bg-brand-dim text-black text-xs font-mono"
          >
            SAVE
          </Button>
        </div>
      )}

      <ul className="space-y-1">
        {profiles.map((p) => {
          const isActive = activeProfile?.id === p.id;
          return (
            <li
              key={p.id}
              className={`group flex items-center justify-between p-2 rounded-sm cursor-pointer border ${
                isActive ? 'bg-[#1a1a1a] border-brand' : 'bg-[#0e0e0e] border-[#1f1f1f] hover:bg-[#151515]'
              }`}
              onClick={() => !isActive && onActivate(p.id)}
              data-testid={`profile-${p.name}`}
            >
              <div className="flex items-center gap-2 min-w-0">
                {isActive ? (
                  <Check className="w-3.5 h-3.5 text-brand flex-none" />
                ) : (
                  <span className="w-3.5 h-3.5 rounded-full border border-[#333] flex-none" />
                )}
                <span className="text-xs font-mono truncate">{p.name}</span>
              </div>
              {!isActive && (
                <button
                  data-testid={LK.deleteProfileBtn}
                  onClick={(e) => { e.stopPropagation(); onDelete(p.id); }}
                  className="opacity-0 group-hover:opacity-100 text-neutral-500 hover:text-danger transition-opacity"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
