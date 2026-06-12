import { Link } from "react-router-dom";
import { LK } from "@/constants/testIds";
import { ArrowLeft, Download, Terminal as TerminalIcon, CheckCircle2 } from "lucide-react";
import { API } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

async function downloadBlob(url, filename) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  } catch (e) {
    toast.error("Download failed", { description: String(e) });
  }
}

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
            Hook up your <span className="text-brand">Launchkey Mini MK4 25</span> to Windows.
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

        <Step n={2} title="Install required packages (one-click)">
          <p className="mb-1">
            <span className="text-brand">Hit the error <span className="font-mono">&ldquo;Preparing metadata (pyproject.toml)&rdquo;</span>?</span>{" "}
            That&apos;s <span className="font-mono">python-rtmidi</span> trying to compile from source.
            Use the installer below — it forces pre-built wheels and avoids the C++ build entirely.
          </p>
          <div className="flex flex-wrap gap-2 my-3">
            <Button
              onClick={() => downloadBlob(`${API}/helper/install-script`, "install_windows.bat")}
              className="rounded-sm bg-brand hover:bg-brand-dim text-black font-mono"
            >
              <Download className="w-4 h-4 mr-2" />
              DOWNLOAD install_windows.bat
            </Button>
            <Button
              onClick={() => downloadBlob(`${API}/helper/requirements`, "requirements.txt")}
              variant="outline"
              className="rounded-sm border-[#262626] bg-surface hover:bg-[#1a1a1a] font-mono"
            >
              <Download className="w-4 h-4 mr-2" />
              requirements.txt
            </Button>
          </div>
          <p>Double-click <span className="font-mono text-white">install_windows.bat</span> — done.</p>
          <p className="mt-3 text-neutral-500">Prefer the manual route?</p>
          <Code>{`python -m pip install --upgrade pip setuptools wheel
python -m pip install mido pycaw comtypes requests pynput
python -m pip install --only-binary=:all: python-rtmidi`}</Code>
          <div className="mt-3 p-3 bg-[#0a0a0a] border border-[#1f1f1f] rounded-sm text-[12px] text-neutral-400">
            <div className="text-warning font-mono mb-1">If python-rtmidi STILL fails:</div>
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Easiest: install <span className="font-mono">Python 3.11 or 3.12</span> (best wheel coverage) and re-run.</li>
              <li>Or install <span className="font-mono">Microsoft C++ Build Tools</span> (workload: &ldquo;Desktop development with C++&rdquo;) then re-run the command.</li>
              <li>Pin a known-good wheel: <span className="font-mono">pip install --only-binary=:all: &quot;python-rtmidi==1.5.8&quot;</span></li>
            </ul>
          </div>
        </Step>

        <Step n={3} title="Download the helper script">
          <Button
            data-testid={LK.downloadScript}
            onClick={() => downloadBlob(`${API}/helper/script`, "launchkey_helper.py")}
            className="rounded-sm bg-brand hover:bg-brand-dim text-black font-mono"
          >
            <Download className="w-4 h-4 mr-2" />
            DOWNLOAD launchkey_helper.py
          </Button>
          <p className="mt-2">Save it next to <span className="font-mono text-white">install_windows.bat</span> (e.g. <span className="font-mono">C:\Tools\</span>).</p>
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
          <Code>{`[MIDI] Opening: Launchkey Mini MK4 25 MIDI
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
