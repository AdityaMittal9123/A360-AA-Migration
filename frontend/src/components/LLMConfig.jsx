import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { PROVIDERS, PROV, STATUS, activeProfile, missingFields, estimateTokens, money } from '../lib/llm';

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
const hl = (s) => esc(s).replace(/("[^"]*")(\s*:)/g, '<span class="k">$1</span>$2').replace(/:\s*("[^"]*")/g, ': <span class="s">$1</span>');

/**
 * Bring Your Own LLM — ONE active model handles every LLM task.
 * cfg / setCfg are the unsaved edits held by Configure; persist() saves them and returns the saved copy.
 */
export default function LLMConfig({ cfg, setCfg, persist, toast, project }) {
  const L = cfg.llm;
  const set = (patch) => setCfg((c) => ({ ...c, llm: { ...c.llm, ...(typeof patch === 'function' ? patch(c.llm) : patch) } }));
  const upd = (id, patch) => set((l) => ({ profiles: l.profiles.map((p) => (p.id === id ? { ...p, ...patch } : p)) }));
  const [editing, setEditing] = useState(null);
  const [picking, setPicking] = useState(false);
  const [preview, setPreview] = useState(null);
  const [calls, setCalls] = useState([]);
  const active = activeProfile(L);

  const loadCalls = () => api.llmCalls(15).then(setCalls).catch(() => {});
  useEffect(() => { loadCalls(); }, []);

  function addProfile(key) {
    const P = PROV(key); const id = key + '-' + Math.random().toString(36).slice(2, 6);
    set((l) => ({ profiles: [...l.profiles, { id, provider: key, label: P.name, apiKey: '', status: 'untested', ...P.defaults }] }));
    setEditing(id); setPicking(false);
  }
  function removeProfile(id) {
    set((l) => ({ profiles: l.profiles.filter((p) => p.id !== id), activeProfile: l.activeProfile === id ? '' : l.activeProfile }));
    toast('Model removed — save to apply.');
  }
  function setActive(id) {
    set((l) => ({ activeProfile: l.activeProfile === id ? '' : id }));
    toast('Active model changed — save to apply.');
  }
  async function test(p) {
    const miss = missingFields(p);
    if (miss.length) { upd(p.id, { status: 'invalid' }); toast(`${p.label}: missing ${miss.join(', ')}`); return; }
    upd(p.id, { status: 'testing' });
    try {
      await persist({ quiet: true });                         // the test runs against the saved profile
      const r = await api.testLLM(p.id);
      upd(p.id, { status: r.ok ? 'ready' : 'failed' });
      toast(r.ok ? `${p.label}: connected in ${r.latency_ms} ms — replied "${r.reply}"` : `${p.label}: ${r.error}`);
      loadCalls();
    } catch (e) { upd(p.id, { status: 'failed' }); toast(e.message); }
  }
  async function showPreview() {
    if (preview) { setPreview(null); return; }
    try { await persist({ quiet: true }); setPreview(await api.llmPreview(project.id)); } catch (e) { toast(e.message); }
  }

  const bots = project?.bots || [];
  const est = estimateTokens(bots);
  const scale = L.projectBots / Math.max(1, bots.length);
  const cost = (p, m = 1) => ((est.tin * (p.costIn || 0) + est.tout * (p.costOut || 0)) / 1e6) * m;

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="note">One model handles <b>every</b> LLM task — functional understanding + recommended target, target re-check, cloud-flow JSON / Robin-script conversion, and GAP assist. Choose it below; with none chosen the pipeline runs entirely on the rule set (no LLM). API keys are stored in the backend database and shown masked here. The system prompt, generation parameters and data-governance rules are fixed server-side.</div>

      {/* 1. Active model + profiles */}
      <div className="card">
        <div className="sectionhead"><h2>Model profiles</h2><span className="s">{L.profiles.length} configured · select ONE as the active model</span></div>
        <div className="grid" style={{ gap: 10 }}>
          {L.profiles.map((p) => {
            const P = PROV(p.provider); const [st, cls] = STATUS[p.status] || STATUS.untested; const open = editing === p.id; const on = L.activeProfile === p.id;
            const F = (f) => P.fields.includes(f);
            return (
              <div key={p.id} className={'profile' + (open ? ' editing' : '')} style={{ borderColor: on ? 'var(--accent)' : undefined }}>
                <div className="row" style={{ gap: 12, flexWrap: 'nowrap' }}>
                  <label className="chk" style={{ margin: 0, padding: 0, border: 'none', flex: 1, minWidth: 0, alignItems: 'center' }}>
                    <input type="radio" name="active-profile" checked={on} onChange={() => setActive(p.id)} />
                    <div style={{ minWidth: 0 }}>
                      <b>{on ? 'Active — one model for all LLM tasks' : 'Use for all LLM tasks'}</b>
                      <span className="inline" style={{ display: 'block', fontSize: 12, color: 'var(--muted)' }}>{P.name} · {p.model || '—'} · {p.endpoint}</span>
                    </div>
                  </label>
                  <span className={'pill ' + cls}>{st}</span>
                  <button className="btn sm" onClick={() => setEditing(open ? null : p.id)}>{open ? 'Done' : 'Edit'}</button>
                  <button className="btn sm" onClick={() => test(p)} disabled={p.status === 'testing'}>Test connection</button>
                  <button className="btn sm" onClick={() => removeProfile(p.id)} aria-label={'Remove ' + p.label}>Remove</button>
                </div>
                {open && (
                  <div className="fields">
                    <div className="field"><label htmlFor={'f-label-' + p.id}>Display name</label><input id={'f-label-' + p.id} type="text" value={p.label} onChange={(e) => upd(p.id, { label: e.target.value })} /></div>
                    {F('endpoint') && <div className="field"><label htmlFor={'f-ep-' + p.id}>Endpoint</label><input id={'f-ep-' + p.id} type="text" value={p.endpoint} onChange={(e) => upd(p.id, { endpoint: e.target.value, status: 'untested' })} />{p.provider === 'azure' && <div className="hint">Your resource base URL, e.g. https://myresource.cognitiveservices.azure.com — a full deployment URL pasted from the portal also works.</div>}</div>}
                    {F('apiKey') && <div className="field"><label htmlFor={'f-key-' + p.id}>{P.keyLabel || 'API key'}{p.provider === 'local' ? ' (optional)' : ''}</label><input id={'f-key-' + p.id} type="password" autoComplete="off" value={p.apiKey || ''} placeholder="Stored server-side, returned masked" onChange={(e) => upd(p.id, { apiKey: e.target.value, status: 'untested' })} /></div>}
                    {F('model') && <div className="field"><label htmlFor={'f-model-' + p.id}>{P.modelLabel || 'Model'}</label><input id={'f-model-' + p.id} type="text" value={p.model} onChange={(e) => upd(p.id, { model: e.target.value, status: 'untested' })} /></div>}
                    {F('apiVersion') && <div className="field"><label htmlFor={'f-ver-' + p.id}>API version</label><input id={'f-ver-' + p.id} type="text" value={p.apiVersion} onChange={(e) => upd(p.id, { apiVersion: e.target.value, status: 'untested' })} /></div>}
                    {F('region') && <div className="field"><label htmlFor={'f-reg-' + p.id}>Region</label><input id={'f-reg-' + p.id} type="text" value={p.region} onChange={(e) => upd(p.id, { region: e.target.value })} /><div className="hint">A public model (OpenAI / Anthropic / Gemini) is allowed under the server-side residency rule.</div></div>}
                    {F('headers') && <div className="field" style={{ gridColumn: '1 / -1' }}><label htmlFor={'f-hd-' + p.id}>Headers (JSON)</label><textarea id={'f-hd-' + p.id} style={{ minHeight: 60 }} value={p.headers} onChange={(e) => upd(p.id, { headers: e.target.value })} /></div>}
                    {F('bodyTemplate') && <div className="field" style={{ gridColumn: '1 / -1' }}><label htmlFor={'f-bt-' + p.id}>Request body template</label><textarea id={'f-bt-' + p.id} style={{ minHeight: 60 }} value={p.bodyTemplate} onChange={(e) => upd(p.id, { bodyTemplate: e.target.value })} /><div className="hint">Placeholders: {'{{system}} {{user}} {{model}} {{apiKey}} {{temperature}} {{maxTokens}}'}</div></div>}
                    {F('responsePath') && <div className="field"><label htmlFor={'f-rp-' + p.id}>Response text path</label><input id={'f-rp-' + p.id} type="text" value={p.responsePath} onChange={(e) => upd(p.id, { responsePath: e.target.value })} /><div className="hint">Dotted path to the text in the JSON response, e.g. choices.0.message.content</div></div>}
                    <div className="field"><label htmlFor={'f-ci-' + p.id}>Input price (USD per 1M tokens)</label><input id={'f-ci-' + p.id} type="number" min="0" step="0.05" value={p.costIn} onChange={(e) => upd(p.id, { costIn: +e.target.value })} /></div>
                    <div className="field"><label htmlFor={'f-co-' + p.id}>Output price (USD per 1M tokens)</label><input id={'f-co-' + p.id} type="number" min="0" step="0.05" value={p.costOut} onChange={(e) => upd(p.id, { costOut: +e.target.value })} /><div className="hint">Indicative — use your contracted rate.</div></div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <div style={{ marginTop: 12 }}>
          {!picking ? <button className="btn" onClick={() => setPicking(true)}>+ Add a model</button> : (
            <div>
              <div className="sectionhead" style={{ marginTop: 4 }}><span className="s">Choose a provider</span><button className="btn sm" onClick={() => setPicking(false)}>Cancel</button></div>
              <div className="prov">{PROVIDERS.map((P) => <button key={P.key} className="provcard" onClick={() => addProfile(P.key)}><div className="mark">{P.mark}</div><div><div style={{ fontWeight: 600 }}>{P.name}</div><div style={{ fontSize: 12, color: 'var(--muted)' }}>{P.tag}</div></div></button>)}</div>
            </div>
          )}
        </div>
        {!active && <div className="note warn" style={{ marginTop: 10 }}>No active model — the Understand and Convert stages run fully on the rule set (rule narrative, rule targets, template conversion). Select a model above and save to turn on all LLM tasks.</div>}
        {active && <div className="note" style={{ marginTop: 10 }}><b>{active.label}</b> handles understanding, target classification, code conversion and GAP assist. If a call fails after retries, the rule set answers so the pipeline never stops.</div>}
      </div>

      {/* 2. Preview */}
      <div className="card">
        <div className="sectionhead"><h2>What gets sent</h2><span className="s">Exact first request after the server-side masking rules are applied — nothing is sent.</span></div>
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn sm" onClick={showPreview} disabled={!project}>{preview ? 'Hide' : 'Preview'} what gets sent</button>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{project ? 'Saves, then shows the first functional-understanding request' : 'Open a project first'}</span>
        </div>
        {preview && (
          <div className="card raised" style={{ marginTop: 10, padding: 0 }}>
            <div className="codehead"><span className="f">{preview.bot} · request 1 of {preview.requests}</span></div>
            <pre className="code" style={{ maxHeight: 340 }} dangerouslySetInnerHTML={{ __html: hl(JSON.stringify({ ...preview.payload, actions: preview.payload.actions.slice(0, 12), more_actions_in_this_request: Math.max(0, preview.payload.actions.length - 12) }, null, 2)) }} />
          </div>
        )}
      </div>

      {/* 3. Cost */}
      <div className="card tbl">
        <div className="sectionhead"><h2>Estimated usage for functional understanding</h2><span className="s">{project ? `${bots.length} bots · ${est.calls} requests · ~${est.tin.toLocaleString()} input / ~${est.tout.toLocaleString()} output tokens` : 'Open a project to estimate'}</span></div>
        {project && <table>
          <thead><tr><th>Model profile</th><th className="num">This project</th><th className="num"><span className="row" style={{ justifyContent: 'flex-end', gap: 6 }}>Projected to <input id="proj-bots" type="number" min="1" style={{ width: 80, padding: '3px 6px' }} value={L.projectBots} onChange={(e) => set({ projectBots: Math.max(1, +e.target.value) })} /> bots</span></th></tr></thead>
          <tbody>
            {L.profiles.map((p) => <tr key={p.id}><td><b>{p.label}</b> <span style={{ color: 'var(--muted)', fontSize: 12 }}>{p.model}</span>{L.activeProfile === p.id && <span className="pill p-ok" style={{ marginLeft: 6 }}>active</span>}</td><td className="num">{money(cost(p))}</td><td className="num">{money(cost(p, scale))}</td></tr>)}
            <tr><td><b>Rules only</b> <span style={{ color: 'var(--muted)', fontSize: 12 }}>no model</span></td><td className="num">$0.00</td><td className="num">$0.00</td></tr>
          </tbody>
        </table>}
      </div>

      {/* 4. Audit */}
      <div className="card tbl">
        <div className="sectionhead"><h2>Recent model calls</h2><span className="s"><button className="btn sm" onClick={loadCalls}>Refresh</button></span></div>
        {calls.length ? <table>
          <thead><tr><th>When</th><th>Task</th><th>Model</th><th>Status</th><th className="num">Latency</th><th>Detail</th></tr></thead>
          <tbody>{calls.map((c) => <tr key={c.id}><td style={{ color: 'var(--muted)' }}>{new Date(c.created_at + 'Z').toLocaleTimeString()}</td><td>{c.task}</td><td>{c.profile}<div style={{ fontSize: 11.5, color: 'var(--muted)' }}>{c.model}</div></td>
            <td><span className={'pill ' + (c.status === 'ok' ? 'p-ok' : c.status === 'blocked' ? 'p-warn' : 'p-high')}>{c.status}</span></td><td className="num">{c.latency_ms} ms</td><td style={{ fontSize: 12, color: 'var(--muted)', maxWidth: 360 }}>{c.error || '—'}</td></tr>)}</tbody>
        </table> : <div className="narr" style={{ color: 'var(--muted)' }}>No model calls yet. They appear here after a connection test or an Understand / Convert run with an active model.</div>}
      </div>
    </div>
  );
}