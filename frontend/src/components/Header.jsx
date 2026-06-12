import { LK } from "@/constants/testIds";
import { Activity, Radio, Settings2, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Header({ helperStatus, midiLearn, learnTarget, onToggleMidiLearn, onCancelLearnTarget, onOpenSetup, onOpenLayoutWizard }) {
  const connected = helperStatus?.helper_connected;
  const port = helperStatus?.helper_info?.midi_port;
  const device = helperStatus?.helper_info?.device_connected;

  return (
    <header
      data-testid={LK.header}
      className="sticky top-0 z-30 bg-base border-b border-[#262626] backdrop-blur-sm"
    >
      <div className="max-w-[1600px] mx-auto px-4 lg:px-8 h-14 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-sm bg-brand flex items-center justify-center">
              <Radio className="w-3.5 h-3.5 text-black" strokeWidth={2.5} />
            </div>
            <div className="font-display font-semibold tracking-tight text-base">
              LAUNCHKEY <span className="text-brand">MIXER</span>
            </div>
          </div>
          <div className="hidden md:block overline">control surface</div>
        </div>

        <div className="flex items-center gap-3">
          {learnTarget && (
            <div
              data-testid="learn-target-badge"
              className="flex items-center gap-2 px-2.5 py-1 rounded-sm border border-brand bg-brand/10 text-[10px] font-mono tracking-wider"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" />
              <span className="text-brand">TARGETING {learnTarget.toUpperCase()}</span>
              <button onClick={onCancelLearnTarget} className="text-neutral-400 hover:text-white">
                <X className="w-3 h-3" />
              </button>
            </div>
          )}
          <div data-testid={LK.helperStatus} className="flex items-center gap-2 text-xs font-mono">
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-success animate-pulse' : 'bg-danger'}`} />
            <span className="text-neutral-400">
              {connected ? 'HELPER ONLINE' : 'HELPER OFFLINE'}
            </span>
            {connected && (
              <span className="text-neutral-600 hidden md:inline">
                · {device ? 'LK ✓' : 'NO MIDI'} {port ? `· ${port}` : ''}
              </span>
            )}
          </div>

          <Button
            data-testid="map-layout-btn"
            onClick={onOpenLayoutWizard}
            variant="outline"
            size="sm"
            className="h-8 rounded-sm border-[#262626] bg-surface hover:bg-[#1a1a1a] font-mono text-xs tracking-wider"
            title="Walk through every control to map the physical device to the UI"
          >
            MAP LAYOUT
          </Button>

          <Button
            data-testid={LK.midiLearnToggle}
            onClick={onToggleMidiLearn}
            variant="outline"
            size="sm"
            className={`h-8 rounded-sm border-[#262626] bg-surface hover:bg-[#1a1a1a] font-mono text-xs tracking-wider ${
              midiLearn ? 'border-brand text-brand pulse-accent' : ''
            }`}
          >
            <Activity className="w-3.5 h-3.5 mr-1.5" />
            {midiLearn ? (learnTarget ? 'WAITING…' : 'CLICK UI THEN PRESS') : 'MIDI LEARN'}
          </Button>

          <Button
            data-testid={LK.connectBtn}
            onClick={onOpenSetup}
            size="sm"
            className="h-8 rounded-sm bg-brand hover:bg-brand-dim text-black font-mono text-xs tracking-wider"
          >
            <Settings2 className="w-3.5 h-3.5 mr-1.5" />
            SETUP
          </Button>
        </div>
      </div>
    </header>
  );
}
