import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { X, SkipForward, CheckCircle2 } from "lucide-react";

// Ordered list of UI positions to walk the user through.
const LAYOUT_STEPS = [
  ...Array.from({ length: 8 }, (_, i) => ({ id: `knob-${i + 1}`, name: `Encoder ${i + 1}`, group: "Knobs" })),
  ...Array.from({ length: 16 }, (_, i) => ({ id: `pad-${i + 1}`, name: `Pad ${i + 1}`, group: "Pads" })),
  { id: "transport-play",  name: "Play",       group: "Transport" },
  { id: "transport-stop",  name: "Stop",       group: "Transport" },
  { id: "transport-record",name: "Record",     group: "Transport" },
  { id: "transport-loop",  name: "Loop",       group: "Transport" },
  { id: "capture-midi",    name: "Capture MIDI",group: "Function" },
  { id: "quantise",        name: "Quantise",   group: "Function" },
  { id: "undo",            name: "Undo",       group: "Function" },
  { id: "shift",           name: "Shift",      group: "Function" },
  { id: "octave-up",       name: "Octave +",   group: "Function" },
  { id: "octave-down",     name: "Octave −",   group: "Function" },
  { id: "track-up",        name: "Track ▶",    group: "Navigation" },
  { id: "track-down",      name: "Track ◀",    group: "Navigation" },
  { id: "scene-up",        name: "Scene ▲",    group: "Navigation" },
  { id: "scene-down",      name: "Scene ▼",    group: "Navigation" },
];

export default function LayoutWizard({ open, profileId, onClose, latestEvent }) {
  const [stepIdx, setStepIdx] = useState(0);
  const [waiting, setWaiting] = useState(true);
  const [lastSinceTs, setLastSinceTs] = useState(null);
  const [lastAcceptedTs, setLastAcceptedTs] = useState(0);
  const step = LAYOUT_STEPS[stepIdx];

  useEffect(() => {
    if (!open) { setStepIdx(0); setWaiting(true); setLastAcceptedTs(0); return; }
    setLastSinceTs(new Date().toISOString());
  }, [open]);

  // Capture next MIDI event after wizard opens, save as alias
  useEffect(() => {
    if (!open || !waiting || !latestEvent || !step) return;
    if (lastSinceTs && latestEvent.timestamp <= lastSinceTs) return;

    // --- Momentary-switch filtering ---
    // Skip releases (note_off, or note_on with velocity 0, or cc=0).
    // Skip aftertouch repeats by debouncing for 800ms after the last capture.
    const ev = latestEvent;
    const isRelease =
      ev.raw_type === "note_off" ||
      (ev.raw_type === "note_on" && (ev.value || 0) === 0) ||
      (ev.raw_type === "control_change" && (ev.value || 0) === 0);
    if (isRelease) return;
    if (Date.now() - lastAcceptedTs < 800) return;

    const physicalId = latestEvent.control_id;
    setLastAcceptedTs(Date.now());
    setWaiting(false);
    (async () => {
      try {
        await api.upsertMapping(profileId, physicalId, {
          action_type: "noop",
          target_app: null,
          params: { layout: true },
          label: step.name,
          ui_alias: step.id,
        });
        toast.success(`${step.name} → ${physicalId}`);
        // Move forward
        setTimeout(() => {
          if (stepIdx + 1 >= LAYOUT_STEPS.length) {
            toast.success("Layout mapped!", { description: "Click any UI control to assign actions." });
            onClose();
          } else {
            setStepIdx(stepIdx + 1);
            setLastSinceTs(latestEvent.timestamp);
            setLastAcceptedTs(Date.now());
            setWaiting(true);
          }
        }, 350);
      } catch (e) {
        toast.error("Save failed", { description: String(e) });
        setWaiting(true);
      }
    })();
  }, [latestEvent, open, waiting, step, stepIdx, profileId, onClose, lastSinceTs, lastAcceptedTs]);

  const skip = () => {
    if (stepIdx + 1 >= LAYOUT_STEPS.length) { onClose(); return; }
    setStepIdx(stepIdx + 1);
    setLastSinceTs(new Date().toISOString());
    setLastAcceptedTs(Date.now());
    setWaiting(true);
  };

  if (!open || !step) return null;
  const pct = Math.round((stepIdx / LAYOUT_STEPS.length) * 100);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="layout-wizard" className="bg-surface border-[#262626] text-white rounded-sm max-w-lg">
        <DialogHeader>
          <div className="overline">map device layout · step {stepIdx + 1} of {LAYOUT_STEPS.length}</div>
          <DialogTitle className="font-display text-2xl">
            Press <span className="text-brand">{step.name}</span> on your Launchkey
          </DialogTitle>
          <DialogDescription className="text-xs text-neutral-500">
            Group: {step.group}. Whatever physical control you press next gets bound to the on-screen <span className="font-mono">{step.id}</span> position.
          </DialogDescription>
        </DialogHeader>

        <div className="py-2 space-y-3">
          <div className="h-1.5 bg-[#0e0e0e] rounded-sm overflow-hidden">
            <div className="h-full bg-brand transition-all" style={{ width: `${pct}%` }} />
          </div>
          <div className="surface p-4 text-center">
            <div className="text-[10px] font-mono text-neutral-500 mb-2 uppercase tracking-widest">waiting for MIDI…</div>
            <div className="w-10 h-10 mx-auto rounded-full border-2 border-brand pulse-accent" />
          </div>
          <div className="text-[11px] font-mono text-neutral-500 leading-relaxed">
            Tip: actions can be assigned later — clicking the UI control will pre-load the right physical binding.
          </div>
        </div>

        <div className="flex justify-between gap-2 pt-2 border-t border-[#262626]">
          <Button variant="ghost" onClick={onClose} className="rounded-sm font-mono text-xs hover:bg-[#1a1a1a]">
            <X className="w-3.5 h-3.5 mr-1.5" /> Cancel
          </Button>
          <div className="flex gap-2">
            <Button onClick={skip} variant="outline" className="rounded-sm font-mono text-xs border-[#262626] hover:bg-[#1a1a1a]">
              <SkipForward className="w-3.5 h-3.5 mr-1.5" /> Skip
            </Button>
            <Button onClick={onClose} className="rounded-sm font-mono text-xs bg-brand hover:bg-brand-dim text-black">
              <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" /> Done
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
