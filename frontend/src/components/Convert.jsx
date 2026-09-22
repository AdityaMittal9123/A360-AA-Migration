import { useEffect, useState } from 'react';
import { api } from '../lib/api';

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
const hl = (s) => esc(s).replace(/("[^"]*")(\s*:)/g, '<span class="k">$1</span>$2').replace(/:\s*("[^"]*")/g, ': <span class="s">$1</span>').replace(/(#.*)$/gm, '<span class="c">$1</span>');

export default function Convert({ project, setProject, toast }) {
  const bots = project.bots;
  const [prog, setProg] = useState(null);
  const [sel, setSel] = useState(bots[0]?.id);
  const [tab, setTab] = useState('cloud');
  const [text, setText] = useState('');
  const cur = bots.find((b) => b.id === sel);
  const art = cur?.artifacts.find((a) => a.kind === tab);
  const reviewed = bots.every((b) => b.groups.length);

  useEffect(() => { if (art) api.artifactText(project.id, art.id).then(setText); else setText(''); }, [art?.id, project.id]);
  useEffect(() => { if (cur && !cur.artifacts.some((a) => a.kind === tab)) setTab('cloud'); }, [sel]);

  async function run() {
    setProg(0);
    for (let i = 0; i < bots.length; i++) {
      try { const bot = await api.convertBot(project.id, bots[i].id); setProject((p) => ({ ...p, bots: p.bots.map((b) => (b.id === bot.id ? bot : b)) })); } catch (e) { toast(`${bots[i].name}: ${e.message}`); }
      setProg(Math.round(((i + 1) / bots.length) * 100));
    }
    setProject(await api.project(project.id)); setProg(null); toast('Conversion complete — artefacts saved to the database');
  }
  const copy = (t) => navigator.clipboard.writeText(t).then(() => toast('Copied to clipboard'), () => toast('Clipboard blocked — select and copy manually'));
  const converted = bots.filter((b) => b.artifacts.length).length;

  return (
    <div>
      <h1>Convert</h1>
      <p className="sub">Cloud flows are emitted as workflow-definition JSON (importable via solution / Logic Apps schema); desktop flows as Robin script for copy-paste into the PAD designer. When a model is routed to <b>code conversion</b> it generates the artefact on top of the same structure; otherwise the deterministic template runs. Anything without a safe mapping is left as a <code>GAP</code> comment for the developer, never silently dropped.</p>
      <div className="card" style={{ marginBottom: 14 }}><div className="row">
        <button className="btn primary" onClick={run} disabled={prog !== null}>{prog === null ? (converted ? 'Re-generate all flows' : 'Generate flows, one bot at a time') : 'Converting…'}</button>
        {prog !== null && <div style={{ flex: 1, minWidth: 160 }}><div className="prog"><i style={{ width: prog + '%' }}></i></div></div>}
        {converted > 0 && <a className="btn" href={api.exportUrl(project.id)}>⬇ Download all artefacts (.zip)</a>}
        {!reviewed && <span className="pill p-warn">Targets not reviewed — rule defaults will be used</span>}
      </div></div>
      {converted > 0 && <div className="two">
        <div className="card" style={{ padding: 8 }}>{bots.map((b) => (
          <button key={b.id} className={'step' + (sel === b.id ? ' on' : '')} onClick={() => setSel(b.id)} disabled={!b.artifacts.length}>
            <span className="n" style={{ fontSize: 10 }}>{b.artifacts.length ? '✓' : '…'}</span>
            <span><div>{b.name}</div><div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 400 }}>{b.recommended_target || 'pending'}{b.artifacts.some((a) => a.kind === 'robin') ? ' · Robin' : ''}{b.artifacts.reduce((s, a) => s + a.gap_count, 0) ? ` · ${b.artifacts.reduce((s, a) => s + a.gap_count, 0)} GAP` : ''}</div></span>
          </button>))}</div>
        <div className="card raised" style={{ minWidth: 0 }}>{cur?.artifacts.length ? <>
          <div className="tabs">
            <button className={'tab' + (tab === 'cloud' ? ' on' : '')} onClick={() => setTab('cloud')}>Cloud flow JSON</button>
            <button className={'tab' + (tab === 'robin' ? ' on' : '')} onClick={() => setTab('robin')} disabled={!cur.artifacts.some((a) => a.kind === 'robin')}>Robin script{cur.artifacts.some((a) => a.kind === 'robin') ? '' : ' (none)'}</button>
          </div>
          {art && <>
            <div className="codehead"><span className="f">{art.filename} · {art.gap_count} GAP</span>
              <span className="row">{tab === 'robin' ? <button className="btn sm primary" onClick={() => copy(text)}>Copy Robin to clipboard</button> : <button className="btn sm" onClick={() => copy(text)}>Copy</button>}<a className="btn sm" href={api.artifactUrl(project.id, art.id)} download={art.filename}>⬇ Download</a></span></div>
            <pre className="code" dangerouslySetInnerHTML={{ __html: hl(text) }} />
            {tab === 'robin' && <div className="note" style={{ marginTop: 10 }}>Open Power Automate for desktop → new flow → click the canvas → <b>Ctrl+V</b>. Then create the input/output variables listed in the header and re-capture each <code>appmask[]</code> UI element. Lines starting with <code># GAP</code> need a developer.</div>}
          </>}
        </> : <div style={{ color: 'var(--muted)' }}>Select a converted bot.</div>}</div>
      </div>}
    </div>
  );
}
