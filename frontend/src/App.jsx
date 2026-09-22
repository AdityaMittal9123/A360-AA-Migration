import { useEffect, useState, useCallback } from 'react';
import { api } from './lib/api';
import { activeProfile } from './lib/llm';
import Upload from './components/Upload';
import Parse from './components/Parse';
import Understand from './components/Understand';
import Convert from './components/Convert';
import Configure from './components/Configure';

const STEPS = [['Upload', 'Drop the A360 export'], ['Parse', 'Task bots, lines, nesting'], ['Understand', 'Narrative & target per bot'], ['Convert', 'Cloud JSON · Robin script'], ['Configure', 'LLM · schemas · mapping']];

export default function App() {
  const [stage, setStage] = useState(0);
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [health, setHealth] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [toast, setToast] = useState(null);
  const showToast = useCallback((m) => { setToast(m); setTimeout(() => setToast(null), 2400); }, []);

  const refreshProjects = useCallback(async () => { try { setProjects(await api.projects()); } catch {} }, []);
  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)); api.config().then(setCfg).catch(() => {}); refreshProjects(); }, [refreshProjects]);

  async function openProject(id) { const p = await api.project(id); setProject(p); return p; }
  async function onUpload(file) {
    try { const p = await api.upload(file); setProject(p); await refreshProjects(); showToast(`Parsed ${p.task_bots} task bot(s)`); setStage(1); }
    catch (e) { showToast(e.message); }
  }

  const done = { 0: !!project, 1: !!project, 2: project && project.bots.every((b) => b.narrative), 3: project && project.bots.some((b) => b.artifacts.length) };
  const rp = activeProfile(cfg?.llm);

  return (
    <div className="app">
      <div className="top">
        <div className="brand">A360 <b>→</b> Power Automate Migration Studio</div>
        <div className="env">
          <span><span className="dot" style={{ background: health ? 'var(--ok)' : 'var(--err)' }}></span> API {health ? 'connected' : 'offline'}</span>
          <span>Parser: server (no LLM)</span>
          <span>LLM: {rp ? `${rp.label} · ${rp.model}${rp.status === 'ready' ? '' : ' (not tested)'}` : 'rules only'}</span>
          <span>Project: {project ? project.name : 'none'}</span>
        </div>
      </div>
      <div className="body">
        <nav className="rail">
          <div className="lbl">Pipeline</div>
          {STEPS.map(([n, d], i) => (
            <button key={n} className={'step' + (stage === i ? ' on' : '') + (done[i] && stage !== i ? ' done' : '') + (i > 0 && i < 4 && !project ? ' locked' : '')} onClick={() => setStage(i)} disabled={i > 0 && i < 4 && !project}>
              <span className="n">{done[i] && stage !== i ? '✓' : i + 1}</span>
              <span><div>{n}</div><div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 400 }}>{d}</div></span>
            </button>
          ))}
          <div style={{ marginTop: 'auto', padding: 10 }}>
            <div className="lbl" style={{ padding: '0 0 6px' }}>Activity</div>
            <div className="log">{project?.runs?.length ? project.runs.slice(-12).map((r, i) => <div key={i}>{new Date(r.created_at).toLocaleTimeString()} {r.stage}: {r.message}</div>) : <div>No project loaded.</div>}</div>
          </div>
        </nav>
        <main className="main">
          {stage === 0 && <Upload onUpload={onUpload} projects={projects} openProject={async (id) => { await openProject(id); setStage(1); }} deleteProject={async (id) => { await api.deleteProject(id); if (project?.id === id) setProject(null); refreshProjects(); }} />}
          {stage === 1 && project && <Parse project={project} next={() => setStage(2)} />}
          {stage === 2 && project && <Understand project={project} setProject={setProject} toast={showToast} next={() => setStage(3)} />}
          {stage === 3 && project && <Convert project={project} setProject={setProject} toast={showToast} />}
          {stage === 4 && <Configure toast={showToast} onSaved={setCfg} project={project} />}
        </main>
      </div>
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
