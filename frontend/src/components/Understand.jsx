import { useState } from 'react';
import { api, TARGETS, TCLS } from '../lib/api';

export default function Understand({ project, setProject, toast, next }) {
  const bots = project.bots;
  const [prog, setProg] = useState(null);
  const [open, setOpen] = useState(bots[0]?.id);
  const ready = bots.every((b) => b.narrative);
  const patchBot = (bot) => setProject((p) => ({ ...p, bots: p.bots.map((b) => (b.id === bot.id ? bot : b)), runs: p.runs }));

  async function run() {
    setProg(0);
    for (let i = 0; i < bots.length; i++) {
      try { const bot = await api.understandBot(project.id, bots[i].id); patchBot(bot); } catch (e) { toast(`${bots[i].name}: ${e.message}`); }
      setProg(Math.round(((i + 1) / bots.length) * 100));
    }
    const fresh = await api.project(project.id); setProject(fresh); setProg(null);
    toast('Functional understanding ready — review targets before converting');
  }
  async function setTarget(gid, target) { try { patchBot(await api.setTarget(project.id, gid, target)); } catch (e) { toast(e.message); } }
  const cur = bots.find((b) => b.id === open);
  const count = (g, t) => g.filter((x) => x.target === t).reduce((s, x) => s + x.count, 0);

  return (
    <div>
      <h1>Functional understanding & target</h1>
      <p className="sub">The model writes what each bot does and recommends a target (cloud / desktop / hybrid); the rule set suggests where each action group should go, and a model can re-check it. The solution architect can override any target before conversion — the override is saved to the database and is what the converter uses.</p>
      {!ready && <div className="card" style={{ marginBottom: 14 }}><div className="row">
        <button className="btn primary" onClick={run} disabled={prog !== null}>{prog === null ? 'Generate understanding' : 'Generating…'}</button>
        {prog !== null && <div style={{ flex: 1, minWidth: 160 }}><div className="prog"><i style={{ width: prog + '%' }}></i></div></div>}
        <span style={{ color: 'var(--muted)', fontSize: 12 }}>{bots.filter((b) => b.narrative).length} / {bots.length} bots · one request per bot</span>
      </div></div>}
      {bots.some((b) => b.narrative) && <div className="card tbl" style={{ padding: 0, marginBottom: 14 }}>
        <table>
          <thead><tr><th>Task bot</th><th>Recommended target</th><th className="num">Cloud</th><th className="num">Desktop</th><th className="num">AI Builder</th><th className="num">Redesign</th><th>Source</th><th></th></tr></thead>
          <tbody>{bots.filter((b) => b.narrative).map((b) => { const edited = b.groups.some((g) => g.target !== g.suggested_target); return (
            <tr key={b.id}><td><b>{b.name}</b></td><td><span className={'pill ' + TCLS[b.recommended_target]}>{b.recommended_target}</span>{edited && <span className="pill p-warn" style={{ marginLeft: 6 }}>edited</span>}</td>
              <td className="num">{count(b.groups, 'Cloud flow')}</td><td className="num">{count(b.groups, 'Desktop flow')}</td><td className="num">{count(b.groups, 'AI Builder')}</td><td className="num">{count(b.groups, 'Redesign')}</td>
              <td><span className={'pill ' + (b.narrative_source && b.narrative_source !== 'rules' ? 'p-ok' : 'p-grey')}>{b.narrative_source}</span>{b.classify_source && b.classify_source !== 'rules' && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>targets: {b.classify_source}</div>}</td>
              <td><button className="btn sm" onClick={() => setOpen(b.id)}>Review</button></td></tr>); })}</tbody>
        </table>
      </div>}
      {cur?.narrative && <div className="card raised">
        <h2>{cur.name}</h2>
        <div className="narr" style={{ marginBottom: 12 }}>{cur.narrative}</div>
        <div className="tbl"><table>
          <thead><tr><th>Action group</th><th className="num">Actions</th><th>Commands</th><th>Suggested</th><th>Approved target</th><th>Reason</th></tr></thead>
          <tbody>{cur.groups.map((g) => (
            <tr key={g.id}><td><b>{g.package}</b></td><td className="num">{g.count}</td><td style={{ color: 'var(--muted)', fontSize: 12 }}>{g.commands}</td>
              <td><span className={'pill ' + TCLS[g.suggested_target]}>{g.suggested_target}</span></td>
              <td><select className="tgt" id={'tgt-' + g.id} value={g.target} onChange={(e) => setTarget(g.id, e.target.value)}>{TARGETS.map((t) => <option key={t}>{t}</option>)}</select></td>
              <td style={{ fontSize: 12, color: 'var(--muted)' }}>{g.reason}</td></tr>))}</tbody>
        </table></div>
      </div>}
      {ready && <div className="row" style={{ marginTop: 16 }}><button className="btn primary" onClick={next}>Approve targets & convert →</button></div>}
    </div>
  );
}
