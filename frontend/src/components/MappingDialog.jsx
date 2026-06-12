import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
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
  { value: "launch_app", label: "Launch App / File / Shortcut", needsTarget: false, kind: "trigger", paramKey: "path", paramLabel: "Path or shortcut", paramPlaceholder: "C:\\Windows\\notepad.exe   OR   spotify   OR   D:\\game.lnk" },
  { value: "kill_app", label: "Close App (force quit by process name)", needsTarget: false, kind: "trigger", paramKey: "process", paramLabel: "Process name", paramPlaceholder: "chrome.exe" },
  { value: "open_url", label: "Open URL in Browser", needsTarget: false, kind: "trigger", paramKey: "url", paramLabel: "URL", paramPlaceholder: "https://youtube.com" },
  { value: "send_keystroke", label: "Send Keystroke / Hotkey", needsTarget: false, kind: "trigger", paramKey: "keys", paramLabel: "Key combo", paramPlaceholder: "ctrl+shift+m  or  alt+f4  or  win+d" },
  { value: "run_command", label: "Run Shell Command", needsTarget: false, kind: "trigger", paramKey: "command", paramLabel: "Command line", paramPlaceholder: 'powershell -c "Get-Date"' },
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
  if (id.startsWith("cc-ch")) {
    const m = id.match(/cc-ch(\d+)-(\d+)/);
    return m ? `Custom CC #${m[2]} (ch ${m[1]})` : id;
  }
  if (id.startsWith("note-ch")) {
    const m = id.match(/note-ch(\d+)-(\d+)/);
    return m ? `Custom Note ${m[2]} (ch ${m[1]})` : id;
  }
  return id.replace(/-/g, ' ');
}

export default function MappingDialog({ controlId, mapping, sessions, onClose, onSave, onDelete }) {
  const [actionType, setActionType] = useState(mapping?.action_type || "set_volume");
  const [target, setTarget] = useState(mapping?.target_app || "");
  const [customTarget, setCustomTarget] = useState(false);
  const [label, setLabel] = useState(mapping?.label || "");
  const [invert, setInvert] = useState(!!mapping?.params?.invert);
  const [uiAlias, setUiAlias] = useState(mapping?.ui_alias || "");
  const [paramValue, setParamValue] = useState("");
  const [triggerOn, setTriggerOn] = useState(mapping?.params?.trigger_on || "press");
  const [ledColor, setLedColor] = useState(
    typeof mapping?.params?.led_color === "number" ? mapping.params.led_color : null
  );

  useEffect(() => {
    setActionType(mapping?.action_type || "set_volume");
    setTarget(mapping?.target_app || "");
    setLabel(mapping?.label || "");
    setInvert(!!mapping?.params?.invert);
    setUiAlias(mapping?.ui_alias || "");
    setCustomTarget(false);
    setTriggerOn(mapping?.params?.trigger_on || "press");
    setLedColor(typeof mapping?.params?.led_color === "number" ? mapping.params.led_color : null);
    const act = ACTION_OPTIONS.find(a => a.value === (mapping?.action_type || "set_volume"));
    setParamValue(act?.paramKey ? (mapping?.params?.[act.paramKey] || "") : "");
  }, [mapping, controlId]);

  const action = useMemo(() => ACTION_OPTIONS.find(a => a.value === actionType), [actionType]);
  const needsTarget = action?.needsTarget;
  const hasParam = !!action?.paramKey;

  const handleSave = () => {
    if (needsTarget && !target.trim()) {
      toast.error("Target app required", { description: "Choose a running app or type a process name." });
      return;
    }
    if (hasParam && !paramValue.trim()) {
      toast.error(`${action.paramLabel} required`, { description: action.paramPlaceholder });
      return;
    }
    const params = {};
    if (action?.kind === "continuous") params.invert = invert;
    if (hasParam) params[action.paramKey] = paramValue.trim();
    if (action?.kind === "trigger" && controlId.startsWith("pad-")) {
      params.trigger_on = triggerOn;
    }
    if (controlId.startsWith("pad-") && ledColor !== null) {
      params.led_color = ledColor;
    }
    onSave({
      action_type: actionType,
      target_app: needsTarget ? target : null,
      params,
      label: label || null,
      ui_alias: uiAlias || null,
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
                {sessions.length > 0 && (
                  <button
                    onClick={() => setCustomTarget(v => !v)}
                    className="text-[10px] font-mono text-brand hover:underline"
                  >
                    {customTarget ? "pick from list" : "enter manually"}
                  </button>
                )}
              </div>
              {sessions.length > 0 && !customTarget ? (
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
              ) : (
                <Input
                  data-testid={LK.mappingTargetInput}
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  placeholder="e.g. chrome.exe, spotify.exe, Discord.exe"
                  className="bg-[#0e0e0e] border-[#262626] rounded-sm h-9 text-sm font-mono"
                />
              )}
            </div>
          )}

          {controlId.startsWith("pad-") && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">Pad LED Color</Label>
                {ledColor !== null && (
                  <button onClick={() => setLedColor(null)} className="text-[10px] font-mono text-brand hover:underline">
                    auto (by action)
                  </button>
                )}
              </div>
              <div className="grid gap-1.5" style={{gridTemplateColumns:'repeat(13,minmax(0,1fr))'}}>
                {[
                  { v: 0,  c: '#000000', n: 'off' },
                  { v: 3,  c: '#ffffff', n: 'white' },
                  { v: 5,  c: '#ff2020', n: 'red' },
                  { v: 9,  c: '#ff8000', n: 'orange' },
                  { v: 13, c: '#ffe000', n: 'yellow' },
                  { v: 17, c: '#a0ff00', n: 'lime' },
                  { v: 21, c: '#10ff10', n: 'green' },
                  { v: 25, c: '#00ffa0', n: 'aqua' },
                  { v: 33, c: '#00d8ff', n: 'cyan' },
                  { v: 41, c: '#2060ff', n: 'blue' },
                  { v: 45, c: '#7030ff', n: 'indigo' },
                  { v: 49, c: '#b040ff', n: 'purple' },
                  { v: 53, c: '#ff40c0', n: 'pink' },
                ].map(sw => {
                  const active = ledColor === sw.v;
                  return (
                    <button
                      key={sw.v}
                      data-testid={`led-${sw.n}`}
                      onClick={() => setLedColor(sw.v)}
                      title={`${sw.n} (velocity ${sw.v})`}
                      className={`aspect-square rounded-sm border-2 transition-all ${
                        active ? 'border-white scale-110' : 'border-[#262626] hover:border-neutral-400'
                      }`}
                      style={{ backgroundColor: sw.c }}
                    />
                  );
                })}
              </div>
              <div className="text-[10px] font-mono text-neutral-500">
                {ledColor === null
                  ? 'auto-picks a color based on the action type'
                  : `velocity ${ledColor} — applied next time the helper syncs (≤1.5s)`}
              </div>
            </div>
          )}

          {action?.kind === "trigger" && controlId.startsWith("pad-") && (
            <div className="space-y-1.5">
              <Label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">Pad Behaviour</Label>
              <Select value={triggerOn} onValueChange={setTriggerOn}>
                <SelectTrigger data-testid="trigger-on-select" className="bg-[#0e0e0e] border-[#262626] rounded-sm h-9 text-sm font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-surface border-[#262626] text-white">
                  <SelectItem value="press" className="text-sm focus:bg-[#1a1a1a]">Fire on Press (momentary, single-shot)</SelectItem>
                  <SelectItem value="release" className="text-sm focus:bg-[#1a1a1a]">Fire on Release</SelectItem>
                  <SelectItem value="while_held" className="text-sm focus:bg-[#1a1a1a]">While Held (mute on press, unmute on release)</SelectItem>
                </SelectContent>
              </Select>
              <div className="text-[10px] font-mono text-neutral-500">
                Velocity is ignored — every tap fires exactly once.
              </div>
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

          {hasParam && (
            <div className="space-y-1.5">
              <Label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">{action.paramLabel}</Label>
              <Input
                data-testid="mapping-param-input"
                value={paramValue}
                onChange={(e) => setParamValue(e.target.value)}
                placeholder={action.paramPlaceholder}
                className="bg-[#0e0e0e] border-[#262626] rounded-sm h-9 text-sm font-mono"
              />
              {action.value === "send_keystroke" && (
                <div className="text-[10px] font-mono text-neutral-500 leading-relaxed">
                  Modifiers: <span className="text-neutral-300">ctrl · shift · alt · win</span> · keys: letters, f1–f12, esc, enter, tab, space, arrows, home, end, pageup, pagedown, delete, backspace.
                </div>
              )}
              {action.value === "launch_app" && (
                <div className="text-[10px] font-mono text-neutral-500">
                  Tip: just type an app name like <span className="text-neutral-300">spotify</span> or <span className="text-neutral-300">notepad</span>, a full path, or a .lnk shortcut.
                </div>
              )}
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

          {uiAlias && (
            <div className="p-3 bg-[#0e0e0e] border border-[#1f1f1f] rounded-sm flex items-center justify-between">
              <div>
                <div className="text-[10px] font-mono text-neutral-500 uppercase tracking-wider">Displays at UI position</div>
                <div className="text-sm font-mono text-brand mt-0.5">{uiAlias}</div>
              </div>
              <Button
                onClick={() => setUiAlias("")}
                variant="ghost" size="sm"
                className="h-7 rounded-sm text-xs font-mono hover:bg-[#1a1a1a] hover:text-danger"
              >
                Unbind UI
              </Button>
            </div>
          )}
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
