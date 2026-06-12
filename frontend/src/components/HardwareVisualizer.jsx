import { useEffect, useState } from "react";
import { LK } from "@/constants/testIds";
import {
  Play, Square, Circle, Repeat, Undo2, Captions, Music2,
  ChevronUp, ChevronDown, ChevronLeft, ChevronRight, ChevronsUp, ChevronsDown,
  MoreHorizontal,
} from "lucide-react";
import CollapsibleSection from "@/components/CollapsibleSection";

// Build N white-key + black-key pattern starting from C (W)
function buildKeys(count = 25) {
  const pattern = ["W","B","W","B","W","W","B","W","B","W","B","W"];
  return Array.from({ length: count }, (_, i) => ({ idx: i + 1, type: pattern[i % 12] }));
}

function Knob({ idx, assigned, flashing, onClick }) {
  const angle = assigned ? 90 : -45;
  return (
    <button
      data-testid={LK.knob(idx)}
      onClick={onClick}
      className={`knob mk4-knob ${assigned ? 'assigned' : ''} ${flashing ? 'pulse-accent' : ''}`}
      title={`Encoder ${idx}${assigned ? ` — ${assigned.label || assigned.action_type}` : ''}`}
    >
      <div className="knob-indicator" style={{ transform: `translateX(-50%) rotate(${angle}deg)` }} />
      <span className="text-[9px] font-mono text-neutral-500 absolute -bottom-4">E{idx}</span>
    </button>
  );
}

function Pad({ idx, assigned, flashing, onClick }) {
  return (
    <button
      data-testid={LK.pad(idx)}
      onClick={onClick}
      className={`pad mk4-pad ${assigned ? 'assigned' : ''} ${flashing ? 'flash' : ''} relative flex items-center justify-center`}
      title={`Pad ${idx}${assigned ? ` — ${assigned.label || assigned.action_type}` : ''}`}
    >
      {assigned && (
        <span className="text-[10px] font-mono text-brand truncate px-1 max-w-full leading-tight">
          {assigned.label || assigned.action_type.replace(/_/g, ' ')}
        </span>
      )}
    </button>
  );
}

function FnBtn({ testid, icon: Icon, assigned, flashing, onClick, label, small = false }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`mk4-btn ${small ? 'h-7 w-9' : 'h-8 w-10'} ${
        assigned ? 'border-brand text-brand' : 'border-[#2a2a2a] text-neutral-400'
      } ${flashing ? 'pulse-accent' : ''}`}
      title={`${label}${assigned ? ` — ${assigned.label || assigned.action_type}` : ''}`}
    >
      <Icon className="w-3.5 h-3.5" />
    </button>
  );
}

function TouchStrip({ testid, label, assigned, flashing, onClick }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`relative w-5 h-28 rounded-sm border ${
        assigned ? 'border-brand' : 'border-[#2a2a2a]'
      } bg-gradient-to-b from-[#1c1c1c] to-[#0a0a0a] ${flashing ? 'pulse-accent' : ''}`}
      title={label}
    >
      <div className="absolute inset-x-0 top-1/2 h-px bg-[#2a2a2a]" />
      <div
        className={`absolute inset-x-0.5 ${assigned ? 'bg-brand' : 'bg-neutral-600'} rounded-sm`}
        style={{ top: '46%', height: '8%' }}
      />
      <span className="absolute -bottom-4 left-1/2 -translate-x-1/2 text-[9px] font-mono text-neutral-500">
        {label}
      </span>
    </button>
  );
}

function ModePill({ label, active = false }) {
  return (
    <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded-sm border tracking-wider ${
      active ? 'border-brand text-brand bg-brand/10' : 'border-[#2a2a2a] text-neutral-500'
    }`}>{label}</span>
  );
}

export default function HardwareVisualizer({ mappingByControl, flashControl, midiLearn, onControlClick }) {
  const keys = buildKeys(25);
  const [activeFlash, setActiveFlash] = useState(null);

  useEffect(() => {
    if (!flashControl) return;
    setActiveFlash(flashControl.id);
    const t = setTimeout(() => setActiveFlash(null), 600);
    return () => clearTimeout(t);
  }, [flashControl]);

  const isFlashing = (id) => activeFlash === id;
  const map = mappingByControl;

  return (
    <CollapsibleSection
      id="hardware"
      title="Novation Launchkey Mini MK4 25"
      defaultOpen
      headerExtra={
        midiLearn ? (
          <span className="text-[10px] font-mono text-brand tracking-widest animate-pulse">◉ MOVE A CONTROL</span>
        ) : (
          <span className="text-[10px] font-mono text-neutral-600">click any control</span>
        )
      }
    >
      <div data-testid={LK.hardware} className={`mk4-shell ${midiLearn ? 'ring-1 ring-brand rounded-md' : ''}`}>

        {/* ROW 1 — Encoders + their mode badges */}
        <div className="mk4-row mb-5">
          <div className="flex items-center justify-between mb-2">
            <div className="overline">8 rotary encoders</div>
            <div className="flex items-center gap-1">
              <span className="text-[10px] font-mono text-neutral-600 mr-1">mode:</span>
              <ModePill label="VOL" active />
              <ModePill label="DEVICE" />
              <ModePill label="PAN" />
              <ModePill label="SEND" />
              <ModePill label="CUSTOM" />
            </div>
          </div>
          <div className="flex gap-3 justify-between pb-5 px-1">
            {Array.from({ length: 8 }, (_, i) => (
              <Knob key={i + 1} idx={i + 1}
                assigned={map[`knob-${i + 1}`]}
                flashing={isFlashing(`knob-${i + 1}`)}
                onClick={() => onControlClick(`knob-${i + 1}`)} />
            ))}
          </div>
        </div>

        {/* ROW 2 — Function buttons strip (transport + capture + nav) */}
        <div className="mk4-row mb-5">
          <div className="overline mb-2">function buttons</div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1">
              <FnBtn testid="settings-btn" icon={MoreHorizontal} label="Settings" assigned={map['settings']}
                flashing={isFlashing('settings')} onClick={() => onControlClick('settings')} small />
              <FnBtn testid="shift-btn" icon={ChevronsUp} label="Shift" assigned={map['shift']}
                flashing={isFlashing('shift')} onClick={() => onControlClick('shift')} small />
            </div>
            <div className="h-6 w-px bg-[#262626]" />
            <span className="overline">transport</span>
            <FnBtn testid={LK.transport('play')} icon={Play} label="Play"
              assigned={map['transport-play']} flashing={isFlashing('transport-play')}
              onClick={() => onControlClick('transport-play')} />
            <FnBtn testid={LK.transport('stop')} icon={Square} label="Stop"
              assigned={map['transport-stop']} flashing={isFlashing('transport-stop')}
              onClick={() => onControlClick('transport-stop')} />
            <FnBtn testid={LK.transport('record')} icon={Circle} label="Record"
              assigned={map['transport-record']} flashing={isFlashing('transport-record')}
              onClick={() => onControlClick('transport-record')} />
            <FnBtn testid={LK.transport('loop')} icon={Repeat} label="Loop"
              assigned={map['transport-loop']} flashing={isFlashing('transport-loop')}
              onClick={() => onControlClick('transport-loop')} />
            <div className="h-6 w-px bg-[#262626]" />
            <FnBtn testid="capture-midi" icon={Captions} label="Capture MIDI"
              assigned={map['capture-midi']} flashing={isFlashing('capture-midi')}
              onClick={() => onControlClick('capture-midi')} />
            <FnBtn testid="quantise-btn" icon={Music2} label="Quantise"
              assigned={map['quantise']} flashing={isFlashing('quantise')}
              onClick={() => onControlClick('quantise')} />
            <FnBtn testid="undo-btn" icon={Undo2} label="Undo"
              assigned={map['undo']} flashing={isFlashing('undo')}
              onClick={() => onControlClick('undo')} />
            <div className="h-6 w-px bg-[#262626]" />
            <span className="overline">nav</span>
            <FnBtn testid={LK.trackDown} icon={ChevronLeft} label="Track ◀"
              assigned={map['track-down']} flashing={isFlashing('track-down')}
              onClick={() => onControlClick('track-down')} />
            <FnBtn testid={LK.trackUp} icon={ChevronRight} label="Track ▶"
              assigned={map['track-up']} flashing={isFlashing('track-up')}
              onClick={() => onControlClick('track-up')} />
            <FnBtn testid={LK.sceneDown} icon={ChevronDown} label="Scene ▼"
              assigned={map['scene-down']} flashing={isFlashing('scene-down')}
              onClick={() => onControlClick('scene-down')} />
            <FnBtn testid={LK.sceneUp} icon={ChevronUp} label="Scene ▲"
              assigned={map['scene-up']} flashing={isFlashing('scene-up')}
              onClick={() => onControlClick('scene-up')} />
          </div>
        </div>

        {/* ROW 3 — Left side (touch strips + octave) | Right side (pads) — physical layout */}
        <div className="grid grid-cols-12 gap-4 mb-2">
          {/* LEFT: pad mode pills + 16 pads on the right of the device */}
          <div className="col-span-12 lg:col-span-7 order-2 lg:order-1">
            <div className="flex items-center justify-between mb-2">
              <div className="overline">16 rgb pads</div>
              <div className="flex items-center gap-1">
                <span className="text-[10px] font-mono text-neutral-600 mr-1">mode:</span>
                <ModePill label="DRUM" active />
                <ModePill label="SESSION" />
                <ModePill label="CHORD" />
                <ModePill label="CUSTOM" />
              </div>
            </div>
            <div className="grid grid-cols-8 gap-1.5">
              {Array.from({ length: 8 }, (_, i) => (
                <Pad key={i + 1} idx={i + 1}
                  assigned={map[`pad-${i + 1}`]} flashing={isFlashing(`pad-${i + 1}`)}
                  onClick={() => onControlClick(`pad-${i + 1}`)} />
              ))}
              {Array.from({ length: 8 }, (_, i) => (
                <Pad key={i + 9} idx={i + 9}
                  assigned={map[`pad-${i + 9}`]} flashing={isFlashing(`pad-${i + 9}`)}
                  onClick={() => onControlClick(`pad-${i + 9}`)} />
              ))}
            </div>
          </div>

          {/* RIGHT (visually moved to left of keys below): Octave + Touch strips */}
          <div className="col-span-12 lg:col-span-5 order-1 lg:order-2 flex gap-4 items-end">
            <div className="flex flex-col items-center gap-2">
              <div className="overline">octave</div>
              <div className="flex gap-1">
                <FnBtn testid="octave-down" icon={ChevronsDown} label="Octave −"
                  assigned={map['octave-down']} flashing={isFlashing('octave-down')}
                  onClick={() => onControlClick('octave-down')} small />
                <FnBtn testid="octave-up" icon={ChevronsUp} label="Octave +"
                  assigned={map['octave-up']} flashing={isFlashing('octave-up')}
                  onClick={() => onControlClick('octave-up')} small />
              </div>
            </div>
            <div className="flex flex-col items-center gap-2 pb-5">
              <div className="overline">touch strips</div>
              <div className="flex gap-2 items-end">
                <TouchStrip testid={LK.pitchWheel} label="PITCH"
                  assigned={map['pitch-wheel']} flashing={isFlashing('pitch-wheel')}
                  onClick={() => onControlClick('pitch-wheel')} />
                <TouchStrip testid={LK.modWheel} label="MOD"
                  assigned={map['mod-wheel']} flashing={isFlashing('mod-wheel')}
                  onClick={() => onControlClick('mod-wheel')} />
              </div>
            </div>
          </div>
        </div>

        {/* ROW 4 — 25 mini keys, full width */}
        <div className="mk4-row mt-1">
          <div className="overline mb-2">25 mini keys · 2 octaves</div>
          <div className="relative flex h-28 select-none">
            {keys.map((k) => (
              <button
                key={k.idx}
                data-testid={LK.key(k.idx)}
                onClick={() => onControlClick(`key-${k.idx}`)}
                className={`key mk4-key ${k.type === 'B' ? 'black' : ''}
                  ${map[`key-${k.idx}`] ? 'assigned' : ''}
                  ${isFlashing(`key-${k.idx}`) ? 'flash' : ''}`}
                title={`Key ${k.idx}`}
              />
            ))}
          </div>
        </div>
      </div>
    </CollapsibleSection>
  );
}
