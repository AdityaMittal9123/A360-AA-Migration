import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import LLMConfig from './LLMConfig';

const TABS = [['llm', 'LLM · bring your own'], ['pa', 'Power Automate schemas'], ['robin', 'Robin mapping']];

export default function Configure({ toast, onSaved, project }) {
  const [tab, setTab] = useState('llm');
  const [cfg, setCfg] = useState(null);
  const [mapText, setMapText] = useState('');
  const [connText, setConnText] = useState('');
  const [dirty, setDirty] = useState(false);
  const load = (c) => { setCfg(c); setMapText(JSON.stringify(c.robin_map, null, 2)); setConnText(JSON.stringify(c.connection_refs, null, 2)); setDirty(false); };
  useEffect(() => { api.config().then(load).catch((e) => toast(e.message)); }, []);
  if (!cfg) return <div className="narr" style={{ color: 'var(--muted)' }}>Loading configuration…</div>;

  const edit = (fn) => { setCfg(fn); setDirty(true); };
  async function persist({ quiet } = {}) {
    const body = { ...cfg, robin_map: JSON.parse(mapText), connection_refs: JSON.parse(connText) };
    body.llm = { ...body.llm, profiles: body.llm.profiles.map(({ status, ...p }) => ({ ...p, status: status === 'testing' ? 'untested' : status })) };
    const saved = await api.saveConfig(body);
    // keep in-flight UI status (e.g. "Testing…") while taking the server's masked keys
    setCfg((c) => ({ ...saved, llm: { ...saved.llm, profiles: saved.llm.profiles.map((p) => ({ ...p, status: c.llm.profiles.find((x) => x.id === p.id)?.status || p.status })) } }));
    setDirty(false); onSaved(saved);
    if (!quiet) toast('Configuration saved');
    return saved;
  }
  const save = () => persist().catch((e) => toast('Not saved: ' + e.message));
  async function reset() { const c = await api.resetConfig(); load(c); onSaved(c); toast('Reset to defaults'); }

  return (
    <div>
      <h1>Configuration</h1>
      <p className="sub">Bring your own model: choose ONE model and it handles every LLM task (understanding, targets, conversion, GAP assist). Schema prefixes, connection references and the Robin mapping are stored in the database; the LLM prompt, generation parameters and data-governance rules are fixed server-side.</p>
      <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={'tab' + (tab === k ? ' on' : '')} onClick={() => setTab(k)}>{l}</button>)}</div>

      {tab === 'llm' && <LLMConfig cfg={cfg} setCfg={edit} persist={persist} toast={toast} project={project} />}

      {tab === 'pa' && (
        <div className="card" style={{ maxWidth: 820 }}>
          <h2>Environment / solution prefix</h2><input id="cfg-prefix" type="text" value={cfg.env_prefix} onChange={(e) => edit((c) => ({ ...c, env_prefix: e.target.value }))} />
          <h2 style={{ marginTop: 16 }}>Cloud flow definition schema</h2><input id="cfg-schema" type="text" value={cfg.cloud_schema} onChange={(e) => edit((c) => ({ ...c, cloud_schema: e.target.value }))} />
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>Export a working flow from your environment, open <code>Workflows/*.json</code>, and paste its <code>$schema</code> here.</div>
          <h2 style={{ marginTop: 16 }}>Connection reference logical names</h2><textarea id="cfg-conn" value={connText} onChange={(e) => { setConnText(e.target.value); setDirty(true); }} style={{ minHeight: 130 }} />
        </div>
      )}

      {tab === 'robin' && (
        <div className="two">
          <div className="card"><h2>PAD schema sample (Robin)</h2><div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>Copy actions from your PAD version and paste here. This is the authoritative syntax for the current release — the GAP assist model also sees it.</div><textarea id="cfg-pad" value={cfg.pad_sample} onChange={(e) => edit((c) => ({ ...c, pad_sample: e.target.value }))} style={{ minHeight: 300 }} /></div>
          <div className="card"><h2>A360 command → Robin mapping</h2><div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>Key: <code>package:command</code> (lower-case). Value: Robin line; <code>{'{attr}'}</code> inserts the A360 attribute as a Robin literal, <code>{'{attr!}'}</code> inserts it raw (for appmask[] names). Unmapped commands become <code># GAP</code> lines.</div><textarea id="cfg-map" value={mapText} onChange={(e) => { setMapText(e.target.value); setDirty(true); }} style={{ minHeight: 300 }} /></div>
        </div>
      )}

      <div className="row" style={{ marginTop: 16, position: 'sticky', bottom: 'env(safe-area-inset-bottom, 0px)', background: 'var(--bg)', padding: '10px 0', borderTop: '1px solid var(--line)' }}>
        <button className="btn primary" onClick={save}>Save configuration</button>
        <button className="btn" onClick={reset}>Reset everything to defaults</button>
        {dirty && <span className="pill p-warn">Unsaved changes</span>}
      </div>
    </div>
  );
}
