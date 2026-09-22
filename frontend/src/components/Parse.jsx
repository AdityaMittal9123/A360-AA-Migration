import { useState } from 'react';
import { CCLS } from '../lib/api';

export default function Parse({ project, next }) {
  const bots = project.bots;
  const [sel, setSel] = useState(bots[0]?.name);
  const b = bots.find((x) => x.name === sel);

  const tree = (name, depth = 0, seen = new Set()) => {
    const bot = bots.find((x) => x.name === name);
    if (!bot) return [<div key={name + depth} style={{ paddingLeft: depth * 18 }}><span className="k">└─ </span>{name} <span className="pill p-warn">not in export</span></div>];
    if (seen.has(name)) return [];
    seen.add(name);
    return [
      <div key={name + depth} style={{ paddingLeft: depth * 18 }}>
        <span className="k">{depth ? '└─ ' : ''}</span>
        <button className="btn sm" style={{ padding: '1px 8px', fontFamily: 'inherit' }} onClick={() => setSel(name)}>{name}</button>{' '}
        <span className="k">{bot.active_actions} active · {bot.disabled_actions} disabled</span>{' '}
        <span className={'pill ' + CCLS[bot.complexity]}>{bot.complexity}</span>
      </div>,
      ...bot.calls.flatMap((c) => tree(c, depth + 1, seen)),
    ];
  };
  const orphans = bots.filter((x) => !project.roots.includes(x.name) && !bots.some((y) => y.calls.includes(x.name)));
  const stats = [[project.task_bots, 'task bots'], [project.active_actions, 'active actions'], [project.disabled_actions, 'disabled actions'], [bots.reduce((s, x) => s + x.variables.length, 0), 'variables'], [new Set(bots.flatMap((x) => Object.keys(x.packages))).size, 'packages'], [bots.reduce((s, x) => s + x.vault_references.length, 0), 'vault refs']];

  return (
    <div>
      <h1>Parsed estate — {project.name}</h1>
      <p className="sub">Deterministic output from <code>parser.py</code>. Complexity = LOC band + weighted action types (variables low, API medium, UI high) + nesting depth. Edit the weights in the parser, not here.</p>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))' }}>
        {stats.map(([v, l]) => <div key={l} className="card stat"><div className="v">{v}</div><div className="l">{l}</div></div>)}
      </div>
      <div className="two" style={{ marginTop: 14 }}>
        <div className="card"><h2>Nesting — which bot calls which</h2><div className="tree">{project.roots.flatMap((r) => tree(r))}{orphans.map((x) => <div key={x.name}><span className="k">(orphan) </span>{x.name}</div>)}</div></div>
        <div className="card"><h2>{b ? b.name : 'Select a bot'}</h2>
          {b ? <div className="kv">
            <span className="k">Active / disabled</span><span>{b.active_actions} / {b.disabled_actions}</span>
            <span className="k">Max nesting depth</span><span>{b.max_nesting_depth}</span>
            <span className="k">Complexity score</span><span>{b.complexity_score} → {b.complexity}</span>
            <span className="k">Packages</span><span>{Object.entries(b.packages).map(([p, n]) => `${p} (${n})`).join(', ')}</span>
            <span className="k">Variables</span><span>{b.variables.map((v) => v.name + (v.input ? ' ⇦' : '') + (v.output ? ' ⇨' : '')).join(', ') || '—'}</span>
            <span className="k">Calls</span><span>{b.calls.join(', ') || '—'}</span>
            <span className="k">Called by</span><span>{b.called_by.join(', ') || '— (root)'}</span>
            <span className="k">Vault refs</span><span>{b.vault_references.join(', ') || '—'}</span>
            <span className="k">Global values</span><span>{b.global_value_references.join(', ') || '—'}</span>
          </div> : <div className="narr" style={{ color: 'var(--muted)' }}>Click a bot in the tree to see its detail.</div>}
        </div>
      </div>
      <div className="card tbl" style={{ marginTop: 14, padding: 0 }}>
        <table>
          <thead><tr><th>Task bot</th><th className="num">Active</th><th className="num">Disabled</th><th className="num">Depth</th><th className="num">Vars</th><th>Top packages</th><th className="num">Score</th><th>Complexity</th></tr></thead>
          <tbody>{bots.map((x) => <tr key={x.id}><td><b>{x.name}</b></td><td className="num">{x.active_actions}</td><td className="num">{x.disabled_actions}</td><td className="num">{x.max_nesting_depth}</td><td className="num">{x.variables.length}</td><td style={{ color: 'var(--muted)' }}>{Object.keys(x.packages).slice(0, 4).join(', ')}</td><td className="num">{x.complexity_score}</td><td><span className={'pill ' + CCLS[x.complexity]}>{x.complexity}</span></td></tr>)}</tbody>
        </table>
      </div>
      <div className="row" style={{ marginTop: 16 }}><button className="btn primary" onClick={next}>Generate functional understanding →</button><span style={{ color: 'var(--muted)', fontSize: 12 }}>Sends parsed actions to the model one bot at a time.</span></div>
    </div>
  );
}
