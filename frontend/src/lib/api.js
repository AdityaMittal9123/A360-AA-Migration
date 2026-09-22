// Thin client over the FastAPI backend. In dev, Vite proxies /api → http://localhost:8000.
const BASE = import.meta.env.VITE_API_BASE || '';

async function req(path, opts = {}) {
  const r = await fetch(BASE + path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.status === 204 ? null : r.json();
}

export const api = {
  health: () => req('/api/health'),
  projects: () => req('/api/projects'),
  project: (id) => req(`/api/projects/${id}`),
  deleteProject: (id) => req(`/api/projects/${id}`, { method: 'DELETE' }),
  upload: (file) => { const fd = new FormData(); fd.append('file', file); return req('/api/projects', { method: 'POST', body: fd }); },
  understandBot: (pid, bid) => req(`/api/projects/${pid}/bots/${bid}/understand`, { method: 'POST' }),
  setTarget: (pid, gid, target) => req(`/api/projects/${pid}/groups/${gid}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target }) }),
  convertBot: (pid, bid) => req(`/api/projects/${pid}/bots/${bid}/convert`, { method: 'POST' }),
  artifactText: async (pid, aid) => (await fetch(`${BASE}/api/projects/${pid}/artifacts/${aid}`)).text(),
  artifactUrl: (pid, aid) => `${BASE}/api/projects/${pid}/artifacts/${aid}`,
  exportUrl: (pid) => `${BASE}/api/projects/${pid}/export.zip`,
  config: () => req('/api/config'),
  saveConfig: (cfg) => req('/api/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) }),
  resetConfig: () => req('/api/config/reset', { method: 'POST' }),
  testLLM: (profileId) => req(`/api/config/llm/test/${encodeURIComponent(profileId)}`, { method: 'POST' }),
  llmCalls: (limit = 30) => req(`/api/config/llm/calls?limit=${limit}`),
  llmPreview: (pid, botId) => req(`/api/projects/${pid}/llm-preview` + (botId ? `?bot_id=${botId}` : '')),
};

export const TARGETS = ['Cloud flow', 'Desktop flow', 'AI Builder', 'Redesign'];
export const TCLS = { 'Cloud flow': 'p-cloud', 'Desktop flow': 'p-desk', 'AI Builder': 'p-ai', 'Redesign': 'p-re', 'Hybrid (cloud + desktop)': 'p-desk' };
export const CCLS = { Low: 'p-low', Medium: 'p-med', High: 'p-high' };
