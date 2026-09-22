// Bring Your Own LLM — provider catalogue and helpers shared by the Configure screen and the header.
// ONE model handles every LLM task; selection is a single activeProfile.
export const PROVIDERS = [
  { key: 'azure', mark: 'AZ', name: 'Azure OpenAI', tag: 'In your Azure tenant', pub: false, modelLabel: 'Deployment name', fields: ['endpoint', 'apiKey', 'model', 'apiVersion', 'region'], defaults: { endpoint: 'https://<resource>.openai.azure.com', model: 'gpt-4o', apiVersion: '2024-10-21', region: 'UK South', costIn: 2.5, costOut: 10 } },
  { key: 'openai', mark: 'OA', name: 'OpenAI', tag: 'Public API', pub: true, fields: ['endpoint', 'apiKey', 'model'], defaults: { endpoint: 'https://api.openai.com/v1', model: 'gpt-4o', costIn: 2.5, costOut: 10 } },
  { key: 'anthropic', mark: 'AN', name: 'Anthropic Claude', tag: 'Public API', pub: true, fields: ['endpoint', 'apiKey', 'model'], defaults: { endpoint: 'https://api.anthropic.com', model: 'claude-sonnet-4-5', costIn: 3, costOut: 15 } },
  { key: 'gemini', mark: 'GE', name: 'Google Gemini', tag: 'OpenAI-compatible endpoint', pub: true, fields: ['endpoint', 'apiKey', 'model'], defaults: { endpoint: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.5-pro', costIn: 1.25, costOut: 10 } },
  { key: 'copilot', mark: 'CS', name: 'Copilot Studio agent', tag: 'Direct Line channel', pub: false, keyLabel: 'Direct Line secret', fields: ['endpoint', 'apiKey'], defaults: { endpoint: 'https://directline.botframework.com/v3/directline', model: '(agent)', costIn: 0, costOut: 0 } },
  { key: 'local', mark: 'LO', name: 'Self-hosted', tag: 'Ollama · vLLM · LM Studio', pub: false, fields: ['endpoint', 'apiKey', 'model'], defaults: { endpoint: 'http://localhost:11434/v1', model: 'llama3.1:70b', costIn: 0, costOut: 0 } },
  { key: 'custom', mark: 'CU', name: 'Custom HTTP', tag: 'Any internal gateway', pub: false, fields: ['endpoint', 'apiKey', 'model', 'headers', 'bodyTemplate', 'responsePath'], defaults: { endpoint: 'https://llm-gateway.corp.internal/v1/generate', model: '', headers: '{"Authorization":"Bearer {{apiKey}}"}', bodyTemplate: '{"model":"{{model}}","system":"{{system}}","input":"{{user}}"}', responsePath: 'output.text', costIn: 0, costOut: 0 } },
];
export const PROV = (k) => PROVIDERS.find((p) => p.key === k) || PROVIDERS[PROVIDERS.length - 1];

// Backend-owned engine settings (mirror of backend services.llm.LLM_PARAMS / LLM_PROMPT).
// Used ONLY for the token/cost estimate — the backend owns the real values.
export const ENGINE = { chunkSize: 150, promptLength: 750, maxTokens: 4000 };

export const STATUS = { untested: ['Not tested', 'p-grey'], invalid: ['Incomplete', 'p-warn'], testing: ['Testing…', 'p-grey'], ready: ['Connected', 'p-ok'], failed: ['Failed', 'p-high'] };

export function missingFields(p) {
  const P = PROV(p.provider); const m = [];
  if (!p.endpoint || p.endpoint.includes('<')) m.push('endpoint');
  if (P.fields.includes('apiKey') && !['custom', 'local'].includes(p.provider) && !p.apiKey) m.push(P.keyLabel || 'API key');
  if (P.fields.includes('model') && p.provider !== 'custom' && !p.model) m.push(P.modelLabel || 'model');
  return m;
}

// The single model used for every LLM task ("" = rules only).
export const activeProfile = (llm) => llm?.profiles.find((p) => p.id === llm?.activeProfile) || null;

// Mirrors backend llm token maths — shown before anything is sent.
export function estimateTokens(bots) {
  let tin = 0, tout = 0, calls = 0;
  bots.forEach((b) => {
    const n = Math.max(1, Math.ceil(b.active_actions / ENGINE.chunkSize));
    calls += n + (n > 1 ? 1 : 0);
    tin += n * (ENGINE.promptLength / 4 + 120 + b.variables.length * 18) + b.active_actions * 34 + (n > 1 ? n * 320 : 0);
    tout += n * 320 + (n > 1 ? 380 : 0);
  });
  return { tin: Math.round(tin), tout: Math.round(tout), calls };
}
export const money = (v) => (v === 0 ? '$0.00' : v < 0.01 ? '< $0.01' : '$' + v.toFixed(2));