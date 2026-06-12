import { useEffect, useMemo, useState } from "react";
import { LK } from "@/constants/testIds";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Trash2 } from "lucide-react";

const ACTION_OPTIONS = [
  { value: "set_volume", label: "Set Volume of App", needsTarget: true, kind: "continuous" },
  { value: "system_volume", label: "Set Master/System Volume", needsTarget: false, kind: "continuous" },
  { value: "toggle_mute", label: "Toggle Mute of App", needsTarget: true, kind: "trigger" },
  { value: "volume_step_up", label: "Step Volume Up (+5%)", needsTarget: true, kind: "trigger" },
  { value: "volume_step_down", label: "Step Volume Down (−5%)", needsTarget: true, kind: "trigger" },
  { value: "media_play_pause", label: "Media · Play / Pause", needsTarget: false, kind: "trigger" },
  { value: "media_next", label: "Media · Next Track", needsTarget: false, kind: "trigger" },
  { value: "media_prev", label: "Media · Previous Track", needsTarget: false, kind: "trigger" },
  { value: "media_stop", label: "Media · Stop", needsTarget: false, kind: "trigger" },
];

function controlLabel(id) {
  if (id.startsWith("knob-")) return `Knob ${id.split('-')[1]}`;
  if (id.startsWith("pad-")) return `Pad ${id.split('-')[1]}`;
  if (id.startsWith("key-")) return `Key ${id.split('-')[1]}`;
  if (id.startsWith("transport-")) return `Transport · ${id.split('-')[1]}`;
  return id.replace(/-/g, ' ');
}

export default function MappingDialog({ controlId, mapping, sessions, onClose, onSave, onDelete }) {
  const [actionType, setActionType] = useState(mapping?.action_type || "set_volume");
  const [target, setTarget] = useState(mapping?.target_app || "");
  const [customTarget, setCustomTarget] = useState(false);
  const [label, setLabel] = useState(mapping?.label || "");
  const [invert, setInvert] = useState(!!mapping?.params?.invert);

  useEffect(() => {
    setActionType(mapping?.action_type || "set_volume");
    setTarget(mapping?.target_app || "");
    setLabel(mapping?.label || "");
    setInvert(!!mapping?.params?.invert);
    setCustomTarget(false);
  }, [mapping, controlId]);

  const action = useMemo(() => ACTION_OPTIONS.find(a => a.value === actionType), [actionType]);
  const needsTarget = action?.needsTarget;

  const handleSave = () => {
    onSave({
      action_type: actionType,
      target_app: needsTarget ? target : null,
      params: action?.kind === "continuous" ? { invert } : {},
      label: label || null,
    });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid={LK.mappingDialog} className="bg-surface border-[#262626] text-white rounded-sm max-w-md">
        <DialogHeader>
          <div className="overline">configure control</div>
          <DialogTitle className="font-display text-xl flex items-center justify-between">
            <span>{controlLabel(controlId)}</span>
            <span className="text-xs font-mono text-neutral-500">{controlId}</span>
          </DialogTitle>
          <DialogDescription className="text-xs text-neutral-500">
            Bind this control to a Windows action. The helper agent will apply it live.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">Action</Label>
            <Select value={actionType} onValueChange={setActionType}>
              <SelectTrigger data-testid={LK.mappingActionSelect} className="bg-[#0e0e0e] border-[#262626] rounded-sm h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-surface border-[#262626] text-white">
                {ACTION_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value} className="text-sm focus:bg-[#1a1a1a]">
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {needsTarget && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">Target App (process name)</Label>
                <button
                  onClick={() => setCustomTarget(v => !v)}
                  className="text-[10px] font-mono text-brand hover:underline"
                >
                  {customTarget ? "pick from list" : "enter manually"}
                </button>
              </div>
              {customTarget || sessions.length === 0 ? (
                <Input
                  data-testid={LK.mappingTargetInput}
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  placeholder="e.g. chrome.exe, spotify.exe, Discord.exe"
                  className="bg-[#0e0e0e] border-[#262626] rounded-sm h-9 text-sm font-mono"
                />
              ) : (
                <Select value={target} onValueChange={setTarget}>
                  <SelectTrigger data-testid={LK.mappingTargetSelect} className="bg-[#0e0e0e] border-[#262626] rounded-sm h-9 text-sm font-mono">
                    <SelectValue placeholder="Select running app…" />
                  </SelectTrigger>
                  <SelectContent className="bg-surface border-[#262626] text-white">
                    {sessions.map((s, i) => (
                      <SelectItem key={i} value={s.process_name} className="text-sm font-mono focus:bg-[#1a1a1a]">
                        {s.display_name || s.process_name}
                        <span className="text-neutral-500 ml-2 text-xs">{s.process_name}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}

          {action?.kind === "continuous" && (
            <div className="flex items-center justify-between p-3 bg-[#0e0e0e] border border-[#1f1f1f] rounded-sm">
              <div>
                <div className="text-sm font-mono">Invert direction</div>
                <div className="text-[11px] text-neutral-500">Reverse low/high values</div>
              </div>
              <Switch checked={invert} onCheckedChange={setInvert} />
            </div>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">Label (optional)</Label>
            <Input
              data-testid={LK.mappingLabel}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Spotify Volume"
              className="bg-[#0e0e0e] border-[#262626] rounded-sm h-9 text-sm font-mono"
            />
          </div>
        </div>

        <DialogFooter className="flex sm:justify-between gap-2">
          {mapping ? (
            <Button
              data-testid={LK.mappingDelete}
              onClick={onDelete}
              variant="outline"
              className="rounded-sm border-[#262626] hover:bg-[#1a1a1a] hover:border-danger hover:text-danger"
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Remove
            </Button>
          ) : <div />}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose} className="rounded-sm hover:bg-[#1a1a1a]">
              Cancel
            </Button>
            <Button
              data-testid={LK.mappingSave}
              onClick={handleSave}
              disabled={needsTarget && !target}
              className="rounded-sm bg-brand hover:bg-brand-dim text-black font-mono"
            >
              SAVE MAPPING
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
