import { useRef, useState } from 'react';

export default function Upload({ onUpload, projects, openProject, deleteProject }) {
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef();
  const handle = async (f) => { if (!f) return; setBusy(true); try { await onUpload(f); } finally { setBusy(false); } };

  return (
    <div>
      <h1>Upload Automation Anywhere export</h1>
      <p className="sub">Export the bot from Control Room with <b>Include dependencies</b> ticked and drop the .zip here. A single task-bot .json also works. Parsing runs on the server with the Python utility — nothing is sent to a model at this step.</p>
      <div className={'drop' + (over ? ' over' : '')} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={(e) => { e.preventDefault(); setOver(false); handle(e.dataTransfer.files[0]); }}>
        <div style={{ fontSize: 34, marginBottom: 6 }}>⬆</div>
        <div><b>{busy ? 'Parsing…' : 'Drop the A360 export (.zip or .json)'}</b></div>
        <div style={{ marginTop: 6 }}>or</div>
        <div className="row" style={{ justifyContent: 'center', marginTop: 10 }}>
          <button className="btn primary" onClick={() => ref.current.click()} disabled={busy}>Choose file</button>
        </div>
        <input ref={ref} id="file-input" type="file" accept=".zip,.json,.abot" hidden onChange={(e) => handle(e.target.files[0])} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', marginTop: 16 }}>
        <div className="card"><h2>What the parser reads</h2><div className="narr">Task bots and sub-task bots · active vs disabled actions · nesting depth · variables (input/output) · packages used · Credential Vault and global value references · which bot calls which.</div></div>
        <div className="card"><h2>What it does not do</h2><div className="narr">No LLM at this stage. Functional narrative and target suggestions come in step 3, one bot per request, so large estates never exceed the model's input limit.</div></div>
        <div className="card"><h2>Sample export</h2><div className="narr">A sample zip is in <code>samples/AR_CashApplication_Main.zip</code> in the repo — upload it to see the full pipeline.</div></div>
      </div>

      {projects.length > 0 && (
        <div className="card tbl" style={{ marginTop: 16, padding: 0 }}>
          <table>
            <thead><tr><th>Previous projects</th><th>Source</th><th>Status</th><th className="num">Bots</th><th className="num">Actions</th><th>Created</th><th></th></tr></thead>
            <tbody>{projects.map((p) => (
              <tr key={p.id}><td><b>{p.name}</b></td><td style={{ color: 'var(--muted)' }}>{p.source_file}</td><td><span className={'pill ' + (p.status === 'converted' ? 'p-ok' : p.status === 'understood' ? 'p-warn' : 'p-grey')}>{p.status}</span></td>
                <td className="num">{p.task_bots}</td><td className="num">{p.active_actions}</td><td style={{ color: 'var(--muted)' }}>{new Date(p.created_at).toLocaleString()}</td>
                <td><span className="row" style={{ gap: 6 }}><button className="btn sm" onClick={() => openProject(p.id)}>Open</button><button className="btn sm" onClick={() => deleteProject(p.id)}>Delete</button></span></td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
