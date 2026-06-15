import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import Header from "@/components/Header";
import SourcesMixerPanel from "@/components/SourcesMixerPanel";
import ProfilesPanel from "@/components/ProfilesPanel";
import HardwareVisualizer from "@/components/HardwareVisualizer";
import EventLog from "@/components/EventLog";
import MappingDialog from "@/components/MappingDialog";
import MappingsList from "@/components/MappingsList";
import CollapsibleSection from "@/components/CollapsibleSection";
import LayoutWizard from "@/components/LayoutWizard";

export default function Dashboard() {
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState([]);
  const [activeProfile, setActiveProfile] = useState(null);
  const [mappings, setMappings] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [browserTabs, setBrowserTabs] = useState([]);
  const [browserConnected, setBrowserConnected] = useState(false);
  const [helperStatus, setHelperStatus] = useState({ helper_connected: false });
  const [events, setEvents] = useState([]);
  const [midiLearn, setMidiLearn] = useState(false);
  const [learnTarget, setLearnTarget] = useState(null);
  const [layoutWizardOpen, setLayoutWizardOpen] = useState(false);
  const [flashControl, setFlashControl] = useState(null);
  const [editingControl, setEditingControl] = useState(null);
  const [latestMidi, setLatestMidi] = useState(null);

  const refreshProfiles = useCallback(async () => {
    const ps = await api.listProfiles();
    setProfiles(ps);
    const active = ps.find(p => p.is_active) || ps[0];
    setActiveProfile(active);
    if (active) {
      const ms = await api.listMappings(active.id);
      setMappings(ms);
    }
  }, []);

  useEffect(() => { refreshProfiles(); }, [refreshProfiles]);

  // poll helper status + sessions every 2s
  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const [st, ss, bt] = await Promise.all([
          api.helperStatus(),
          api.helperSessions(),
          api.browserTabs().catch(() => ({ tabs: [], connected: false })),
        ]);
        if (stop) return;
        setHelperStatus(st);
        setSessions(ss.sessions || []);
        setBrowserTabs(bt.tabs || []);
        setBrowserConnected(!!bt.connected);
      } catch (e) { /* offline */ }
    }
    tick();
    const id = setInterval(tick, 2000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  // poll MIDI events
  useEffect(() => {
    let stop = false;
    let since = new Date().toISOString();
    async function tick() {
      try {
        const data = await api.helperEvents(since);
        if (stop) return;
        if (data.events && data.events.length) {
          since = data.events[data.events.length - 1].timestamp;
          setEvents((prev) => [...prev, ...data.events].slice(-100));
          const latest = data.events[data.events.length - 1];
          setFlashControl({ id: latest.control_id, ts: Date.now() });
          setLatestMidi(latest);
          // Targeted learn: physical event captured, bind to chosen UI control
          if (learnTarget) {
            const physicalId = latest.control_id;
            // Save mapping using physical id as the dispatch key, ui_alias = target
            (async () => {
              try {
                const m = await api.upsertMapping(activeProfile.id, physicalId, {
                  action_type: "set_volume",
                  target_app: null,
                  params: {},
                  label: null,
                  ui_alias: learnTarget,
                });
                setMappings((prev) => [...prev.filter(x => x.control_id !== physicalId), m]);
                toast.success(`Bound ${physicalId} → ${learnTarget}`, { description: "Finish configuring the action." });
                setEditingControl(physicalId);
              } catch (e) {
                toast.error("Bind failed", { description: String(e) });
              }
              setLearnTarget(null);
              setMidiLearn(false);
            })();
          } else if (midiLearn) {
            setEditingControl(latest.control_id);
            setMidiLearn(false);
            toast("MIDI Learn captured", { description: latest.control_id });
          }
        }
      } catch (e) { /* offline */ }
    }
    tick();
    const id = setInterval(tick, 250);
    return () => { stop = true; clearInterval(id); };
  }, [midiLearn, learnTarget, activeProfile]);

  const mappingByControl = useMemo(() => {
    const m = {};
    mappings.forEach(x => {
      // Mapping is "owned" by its control_id, but display also at ui_alias if set.
      m[x.control_id] = x;
      if (x.ui_alias && !m[x.ui_alias]) m[x.ui_alias] = x;
    });
    return m;
  }, [mappings]);

  const onControlClick = (controlId) => {
    if (midiLearn) {
      setLearnTarget(controlId);
      toast(`Targeting ${controlId}`, { description: "Now press the matching control on your device." });
      return;
    }
    // If a layout alias exists (ui_alias === controlId, action_type === noop),
    // pre-open editing for the aliased physical id so user just configures the action.
    const aliased = mappings.find(m => m.ui_alias === controlId && m.action_type === "noop");
    if (aliased) {
      setEditingControl(aliased.control_id);
      return;
    }
    setEditingControl(controlId);
  };

  const saveMapping = async (controlId, body) => {
    const m = await api.upsertMapping(activeProfile.id, controlId, body);
    setMappings(prev => {
      const others = prev.filter(x => x.control_id !== controlId);
      return [...others, m];
    });
    toast.success("Mapping saved", { description: controlId });
  };

  const deleteMapping = async (controlId) => {
    await api.deleteMapping(activeProfile.id, controlId);
    setMappings(prev => prev.filter(x => x.control_id !== controlId));
    toast("Mapping removed", { description: controlId });
  };

  return (
    <div className="min-h-screen bg-base text-white">
      <Header
        helperStatus={helperStatus}
        midiLearn={midiLearn}
        learnTarget={learnTarget}
        onToggleMidiLearn={() => { setMidiLearn(v => !v); setLearnTarget(null); }}
        onCancelLearnTarget={() => setLearnTarget(null)}
        onOpenSetup={() => navigate("/setup")}
        onOpenLayoutWizard={() => setLayoutWizardOpen(true)}
      />

      <main className="px-4 lg:px-8 py-6 max-w-[1600px] mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <aside className="lg:col-span-3 space-y-4">
            <CollapsibleSection id="profiles" title="macro profiles" defaultOpen>
              <ProfilesPanel
                profiles={profiles}
                activeProfile={activeProfile}
                onActivate={async (id) => { await api.activateProfile(id); await refreshProfiles(); }}
                onCreate={async (name) => { await api.createProfile(name); await refreshProfiles(); toast.success("Profile created"); }}
                onDelete={async (id) => { await api.deleteProfile(id); await refreshProfiles(); toast("Profile deleted"); }}
              />
            </CollapsibleSection>

            <CollapsibleSection
              id="mappings"
              title="active mappings"
              defaultOpen
              headerExtra={
                <span className="text-[10px] font-mono text-neutral-600">{mappings.length} bound</span>
              }
            >
              <MappingsList
                mappings={mappings}
                onEdit={(id) => setEditingControl(id)}
                onDelete={deleteMapping}
              />
            </CollapsibleSection>

            <CollapsibleSection id="sessions" title="sources mixer" defaultOpen>
              <SourcesMixerPanel
                sessions={sessions}
                browserTabs={browserTabs}
                mappings={mappings}
                helperConnected={helperStatus.helper_connected}
                browserConnected={browserConnected}
              />
            </CollapsibleSection>
          </aside>

          <section className="lg:col-span-9 space-y-4">
            <HardwareVisualizer
              mappingByControl={mappingByControl}
              flashControl={flashControl}
              midiLearn={midiLearn}
              learnTarget={learnTarget}
              sessions={sessions}
              browserTabs={browserTabs}
              onControlClick={onControlClick}
            />
            <CollapsibleSection
              id="events"
              title="event stream"
              defaultOpen={false}
              headerExtra={
                <span className="text-[10px] font-mono text-neutral-600">{events.length} events</span>
              }
            >
              <EventLog events={events} />
            </CollapsibleSection>
          </section>
        </div>
      </main>

      {editingControl && activeProfile && (
        <MappingDialog
          controlId={editingControl}
          mapping={mappingByControl[editingControl]}
          sessions={sessions}
          browserTabs={browserTabs}
          onClose={() => setEditingControl(null)}
          onSave={(body) => { saveMapping(editingControl, body); setEditingControl(null); }}
          onDelete={() => { deleteMapping(editingControl); setEditingControl(null); }}
        />
      )}
      {activeProfile && (
        <LayoutWizard
          open={layoutWizardOpen}
          profileId={activeProfile.id}
          onClose={async () => {
            setLayoutWizardOpen(false);
            const ms = await api.listMappings(activeProfile.id);
            setMappings(ms);
          }}
          latestEvent={latestMidi}
        />
      )}
    </div>
  );
}
