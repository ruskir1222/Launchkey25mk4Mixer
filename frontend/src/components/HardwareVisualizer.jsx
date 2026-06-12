import { useEffect, useState } from "react";
import { LK } from "@/constants/testIds";
import {
  Play, Square, Circle, Repeat, Undo2, Captions,
  ChevronUp, ChevronDown, Music2,
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
      className={`knob ${assigned ? 'assigned' : ''} ${flashing ? 'pulse-accent' : ''}`}
      title={`Knob ${idx}${assigned ? ` — ${assigned.label || assigned.action_type}` : ''}`}
    >
      <div className="knob-indicator" style={{ transform: `translateX(-50%) rotate(${angle}deg)` }} />
      <span className="text-[9px] font-mono text-neutral-500 absolute -bottom-4">K{idx}</span>
    </button>
  );
}

function Pad({ idx, assigned, flashing, onClick }) {
  return (
    <button
      data-testid={LK.pad(idx)}
      onClick={onClick}
      className={`pad ${assigned ? 'assigned' : ''} ${flashing ? 'flash' : ''} relative flex items-center justify-center`}
      title={`Pad ${idx}${assigned ? ` — ${assigned.label || assigned.action_type}` : ''}`}
    >
      <span className="text-[9px] font-mono text-neutral-500 absolute top-1 left-1.5">P{idx}</span>
      {assigned && (
        <span className="text-[10px] font-mono text-brand truncate px-1 max-w-full">
          {assigned.label || assigned.action_type.replace(/_/g, ' ')}
        </span>
      )}
    </button>
  );
}

function ActionBtn({ testid, icon: Icon, assigned, flashing, onClick, label }) {
  return (
    <button
      data-testid={testid}
      onClick={onClick}
      className={`surface-hover h-9 w-12 rounded-sm border flex items-center justify-center ${
        assigned ? 'border-brand text-brand' : 'border-[#262626] text-neutral-400'
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
      className={`relative w-6 h-32 rounded-sm border ${
        assigned ? 'border-brand' : 'border-[#262626]'
      } bg-gradient-to-b from-[#1a1a1a] to-[#0a0a0a] ${flashing ? 'pulse-accent' : ''}`}
      title={label}
    >
      <div className="absolute inset-x-0 top-1/2 h-px bg-[#2a2a2a]" />
      <div
        className={`absolute inset-x-1 ${assigned ? 'bg-brand' : 'bg-neutral-700'} rounded-sm`}
        style={{ top: '46%', height: '8%' }}
      />
      <span className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] font-mono text-neutral-500 whitespace-nowrap">
        {label}
      </span>
    </button>
  );
}

export default function HardwareVisualizer({ mappingByControl, flashControl, midiLearn, onControlClick }) {
  const keys = buildKeys(25); // <-- Mini MK4 has 25 keys
  const [activeFlash, setActiveFlash] = useState(null);

  useEffect(() => {
    if (!flashControl) return;
    setActiveFlash(flashControl.id);
    const t = setTimeout(() => setActiveFlash(null), 600);
    return () => clearTimeout(t);
  }, [flashControl]);

  const isFlashing = (id) => activeFlash === id;

  return (
    <CollapsibleSection
      id="hardware"
      title="Novation Launchkey Mini MK4 25"
      defaultOpen={true}
      headerExtra={
        midiLearn ? (
          <span className="text-[10px] font-mono text-brand tracking-widest animate-pulse">
            ◉ MOVE A CONTROL
          </span>
        ) : (
          <span className="text-[10px] font-mono text-neutral-600">click any control</span>
        )
      }
    >
      <div data-testid={LK.hardware} className={`${midiLearn ? 'ring-1 ring-brand rounded-sm' : ''}`}>

        {/* Knobs + Pads row */}
        <div className="grid grid-cols-12 gap-6 mb-5">
          <div className="col-span-12 lg:col-span-5">
            <div className="overline mb-2">rotary encoders</div>
            <div className="flex gap-2 justify-between pb-5">
              {Array.from({ length: 8 }, (_, i) => (
                <Knob key={i + 1} idx={i + 1}
                  assigned={mappingByControl[`knob-${i + 1}`]}
                  flashing={isFlashing(`knob-${i + 1}`)}
                  onClick={() => onControlClick(`knob-${i + 1}`)} />
              ))}
            </div>
          </div>

          <div className="col-span-12 lg:col-span-7">
            <div className="overline mb-2">rgb pads (drum mode)</div>
            <div className="grid grid-cols-8 gap-2">
              {Array.from({ length: 8 }, (_, i) => (
                <Pad key={i + 1} idx={i + 1}
                  assigned={mappingByControl[`pad-${i + 1}`]}
                  flashing={isFlashing(`pad-${i + 1}`)}
                  onClick={() => onControlClick(`pad-${i + 1}`)} />
              ))}
              {Array.from({ length: 8 }, (_, i) => (
                <Pad key={i + 9} idx={i + 9}
                  assigned={mappingByControl[`pad-${i + 9}`]}
                  flashing={isFlashing(`pad-${i + 9}`)}
                  onClick={() => onControlClick(`pad-${i + 9}`)} />
              ))}
            </div>
          </div>
        </div>

        {/* Transport / nav row */}
        <div className="flex flex-wrap items-center gap-3 mb-5 pb-4 border-b border-[#1a1a1a]">
          <div className="overline mr-1">transport</div>
          <ActionBtn testid={LK.transport('play')} icon={Play} label="Play"
            assigned={mappingByControl['transport-play']}
            flashing={isFlashing('transport-play')}
            onClick={() => onControlClick('transport-play')} />
          <ActionBtn testid={LK.transport('stop')} icon={Square} label="Stop"
            assigned={mappingByControl['transport-stop']}
            flashing={isFlashing('transport-stop')}
            onClick={() => onControlClick('transport-stop')} />
          <ActionBtn testid={LK.transport('record')} icon={Circle} label="Record"
            assigned={mappingByControl['transport-record']}
            flashing={isFlashing('transport-record')}
            onClick={() => onControlClick('transport-record')} />
          <ActionBtn testid={LK.transport('loop')} icon={Repeat} label="Loop"
            assigned={mappingByControl['transport-loop']}
            flashing={isFlashing('transport-loop')}
            onClick={() => onControlClick('transport-loop')} />

          <div className="mx-3 h-7 w-px bg-[#262626]" />
          <div className="overline mr-1">capture</div>
          <ActionBtn testid="capture-midi" icon={Captions} label="Capture MIDI"
            assigned={mappingByControl['capture-midi']}
            flashing={isFlashing('capture-midi')}
            onClick={() => onControlClick('capture-midi')} />
          <ActionBtn testid="undo" icon={Undo2} label="Undo"
            assigned={mappingByControl['undo']}
            flashing={isFlashing('undo')}
            onClick={() => onControlClick('undo')} />
          <ActionBtn testid="quantize" icon={Music2} label="Quantize"
            assigned={mappingByControl['quantize']}
            flashing={isFlashing('quantize')}
            onClick={() => onControlClick('quantize')} />

          <div className="mx-3 h-7 w-px bg-[#262626]" />
          <div className="overline mr-1">track</div>
          <ActionBtn testid={LK.trackDown} icon={ChevronDown} label="Track Down"
            assigned={mappingByControl['track-down']}
            flashing={isFlashing('track-down')}
            onClick={() => onControlClick('track-down')} />
          <ActionBtn testid={LK.trackUp} icon={ChevronUp} label="Track Up"
            assigned={mappingByControl['track-up']}
            flashing={isFlashing('track-up')}
            onClick={() => onControlClick('track-up')} />
          <div className="overline mr-1 ml-1">scene</div>
          <ActionBtn testid={LK.sceneDown} icon={ChevronDown} label="Scene Down"
            assigned={mappingByControl['scene-down']}
            flashing={isFlashing('scene-down')}
            onClick={() => onControlClick('scene-down')} />
          <ActionBtn testid={LK.sceneUp} icon={ChevronUp} label="Scene Up"
            assigned={mappingByControl['scene-up']}
            flashing={isFlashing('scene-up')}
            onClick={() => onControlClick('scene-up')} />
        </div>

        {/* Touch strips + 25 keys */}
        <div className="flex items-end gap-4">
          <div className="flex flex-col items-center gap-2 pb-2">
            <div className="overline">touch strips</div>
            <div className="flex gap-2 items-end">
              <TouchStrip testid={LK.pitchWheel} label="PITCH"
                assigned={mappingByControl['pitch-wheel']}
                flashing={isFlashing('pitch-wheel')}
                onClick={() => onControlClick('pitch-wheel')} />
              <TouchStrip testid={LK.modWheel} label="MOD"
                assigned={mappingByControl['mod-wheel']}
                flashing={isFlashing('mod-wheel')}
                onClick={() => onControlClick('mod-wheel')} />
            </div>
          </div>

          <div className="flex-1 overflow-hidden">
            <div className="overline mb-2">keys (25 · 2 octaves)</div>
            <div className="relative flex h-32 select-none">
              {keys.map((k) => (
                <button
                  key={k.idx}
                  data-testid={LK.key(k.idx)}
                  onClick={() => onControlClick(`key-${k.idx}`)}
                  className={`key ${k.type === 'B' ? 'black' : ''}
                    ${mappingByControl[`key-${k.idx}`] ? 'assigned' : ''}
                    ${isFlashing(`key-${k.idx}`) ? 'flash' : ''}`}
                  title={`Key ${k.idx}`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </CollapsibleSection>
  );
}
