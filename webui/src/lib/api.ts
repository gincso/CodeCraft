const API_BASE = "";

async function request(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  health: () => request("/health"),
  info: () => request("/api/info"),
  projects: { list: () => request("/api/projects"), create: (data: { name: string; description: string; mode: string }) => request("/api/projects", { method: "POST", body: JSON.stringify(data) }), },
  run: { start: (projectPath: string, mode: string) => request("/api/run", { method: "POST", body: JSON.stringify({ project_path: projectPath, mode }), }), status: (runId: string) => request(`/api/run/${runId}`), cancel: (runId: string) => request(`/api/run/${runId}/cancel`, { method: "POST" }), },
  agents: () => request("/api/agents"),
  memory: { stats: () => request("/api/memory"), search: (agent: string, query: string) => request("/api/memory/search", { method: "POST", body: JSON.stringify({ agent, query }), }), },
};
