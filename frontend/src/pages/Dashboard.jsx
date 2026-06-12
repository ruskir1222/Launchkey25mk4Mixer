import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import Header from "@/components/Header";
import SessionsPanel from "@/components/SessionsPanel";
import ProfilesPanel from "@/components/ProfilesPanel";
import HardwareVisualizer from "@/components/HardwareVisualizer";
import EventLog from "@/components/EventLog";
import MappingDialog from "@/components/MappingDialog";
import MappingsList from "@/components/MappingsList";

export default function Dashboard() {
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState([]);
  const [activeProfile, setActiveProfile] = useState(null);
  const [mappings, setMappings] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [helperStatus, setHelperStatus] = useState({ helper_connected: false });
  const [events, setEvents] = useState([]);
  const [midiLearn, setMidiLearn] = useState(false);
  const [flashControl, setFlashControl] = useState(null);
  const [editingControl, setEditingControl] = useState(null);

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
        const [st, ss] = await Promise.all([api.helperStatus(), api.helperSessions()]);
        if (stop) return;
        setHelperStatus(st);
        setSessions(ss.sessions || []);
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
          if (midiLearn) {
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
  }, [midiLearn]);

  const mappingByControl = useMemo(() => {
    const m = {};
    mappings.forEach(x => { m[x.control_id] = x; });
    return m;
  }, [mappings]);

  const onControlClick = (controlId) => setEditingControl(controlId);

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
        onToggleMidiLearn={() => setMidiLearn(v => !v)}
        onOpenSetup={() => navigate("/setup")}
      />

      <main className="px-4 lg:px-8 py-6 max-w-[1600px] mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <aside className="lg:col-span-3 space-y-4">
            <ProfilesPanel
              profiles={profiles}
              activeProfile={activeProfile}
              onActivate={async (id) => { await api.activateProfile(id); await refreshProfiles(); }}
              onCreate={async (name) => { await api.createProfile(name); await refreshProfiles(); toast.success("Profile created"); }}
              onDelete={async (id) => { await api.deleteProfile(id); await refreshProfiles(); toast("Profile deleted"); }}
            />
            <MappingsList
              mappings={mappings}
              onEdit={(id) => setEditingControl(id)}
              onDelete={deleteMapping}
            />
            <SessionsPanel sessions={sessions} helperConnected={helperStatus.helper_connected} />
          </aside>

          <section className="lg:col-span-9 space-y-4">
            <HardwareVisualizer
              mappingByControl={mappingByControl}
              flashControl={flashControl}
              midiLearn={midiLearn}
              onControlClick={onControlClick}
            />
            <EventLog events={events} />
          </section>
        </div>
      </main>

      {editingControl && activeProfile && (
        <MappingDialog
          controlId={editingControl}
          mapping={mappingByControl[editingControl]}
          sessions={sessions}
          onClose={() => setEditingControl(null)}
          onSave={(body) => { saveMapping(editingControl, body); setEditingControl(null); }}
          onDelete={() => { deleteMapping(editingControl); setEditingControl(null); }}
        />
      )}
    </div>
  );
}
