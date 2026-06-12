import { Link } from "react-router-dom";
import { LK } from "@/constants/testIds";
import { ArrowLeft, Download, Terminal as TerminalIcon, CheckCircle2 } from "lucide-react";
import { API } from "@/lib/api";
import { Button } from "@/components/ui/button";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function Code({ children }) {
  return (
    <pre className="bg-[#0a0a0a] border border-[#1f1f1f] rounded-sm p-3 text-[12px] font-mono text-neutral-300 overflow-x-auto">
      <code>{children}</code>
    </pre>
  );
}

function Step({ n, title, children }) {
  return (
    <div className="surface p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-7 h-7 rounded-sm bg-brand text-black font-mono font-semibold flex items-center justify-center">
          {n}
        </div>
        <h3 className="font-display text-lg">{title}</h3>
      </div>
      <div className="text-sm text-neutral-400 space-y-2 leading-relaxed">{children}</div>
    </div>
  );
}

export default function Setup() {
  return (
    <div data-testid={LK.setupPage} className="min-h-screen bg-base">
      <header className="border-b border-[#262626]">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-sm font-mono text-neutral-400 hover:text-white">
            <ArrowLeft className="w-4 h-4" /> back to dashboard
          </Link>
          <div className="overline">windows helper setup</div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10 space-y-6">
        <section>
          <div className="overline mb-3">step-by-step</div>
          <h1 className="font-display text-4xl sm:text-5xl font-semibold mb-3">
            Hook up your <span className="text-brand">Launchkey 37</span> to Windows.
          </h1>
          <p className="text-neutral-400 max-w-2xl">
            Per-app volume control needs a tiny local agent. This dashboard sends your mapping profiles to a small Python script
            running on your PC. The script talks to your Launchkey via MIDI and changes Windows audio sessions in real time.
          </p>
        </section>

        <Step n={1} title="Install Python 3.10 or newer">
          Grab it from <a className="text-brand underline" href="https://www.python.org/downloads/" target="_blank" rel="noreferrer">python.org</a>.
          During install, check the &ldquo;Add Python to PATH&rdquo; option.
        </Step>

        <Step n={2} title="Install required packages">
          Open <span className="font-mono text-white">PowerShell</span> or <span className="font-mono text-white">cmd</span> and run:
          <Code>pip install mido python-rtmidi pycaw comtypes requests pynput</Code>
        </Step>

        <Step n={3} title="Download the helper script">
          <a href={`${API}/helper/script`} download>
            <Button data-testid={LK.downloadScript} className="rounded-sm bg-brand hover:bg-brand-dim text-black font-mono">
              <Download className="w-4 h-4 mr-2" />
              DOWNLOAD launchkey_helper.py
            </Button>
          </a>
          <p className="mt-2">Save it anywhere convenient (e.g. <span className="font-mono">C:\Tools\</span>).</p>
        </Step>

        <Step n={4} title="Point the helper at this dashboard">
          Your dashboard API URL is:
          <Code>{BACKEND_URL}</Code>
          Set it as an environment variable (one-time):
          <Code>setx LAUNCHKEY_API_URL "{BACKEND_URL}"</Code>
          Or pass it on the command line each time.
        </Step>

        <Step n={5} title="Plug in your Launchkey and run the helper">
          <Code>{`python launchkey_helper.py --api "${BACKEND_URL}"`}</Code>
          You should see something like:
          <Code>{`[MIDI] Opening port: Launchkey 37 MK3 LKMK3 MIDI
[Launchkey Mixer] Helper running. Dashboard API: ${BACKEND_URL}`}</Code>
        </Step>

        <Step n={6} title="You are live">
          <div className="flex items-center gap-2 text-success">
            <CheckCircle2 className="w-4 h-4" /> Head back to the dashboard. The status dot in the header turns green.
          </div>
          <p>
            Click any knob, pad or key on the on-screen Launchkey to assign it to an app. Or hit{" "}
            <span className="font-mono text-white">MIDI LEARN</span> and physically wiggle a control. The dashboard will jump
            to whatever you touched.
          </p>
        </Step>

        <div className="surface p-5">
          <div className="flex items-center gap-2 mb-2">
            <TerminalIcon className="w-4 h-4 text-brand" />
            <div className="overline">troubleshooting</div>
          </div>
          <ul className="text-sm text-neutral-400 space-y-1.5 list-disc pl-5">
            <li>Make sure Novation Components / DAW software isn't grabbing the device exclusively.</li>
            <li>If your Launchkey uses different CC numbers, edit <span className="font-mono">MIDI_MAP_OVERRIDES</span> at the top of the script.</li>
            <li>Run the script as Administrator if some apps' volumes refuse to change.</li>
            <li>Per-app volume only works while the target app actually has an active audio session.</li>
          </ul>
        </div>
      </main>
    </div>
  );
}
