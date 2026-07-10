import { useState, useEffect } from "react";
import { api } from "../lib/api";

export default function AdminPanel() {
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);
  const [providers, setProviders] = useState<Array<Record<string, unknown>>>([]);
  const [memStats, setMemStats] = useState<Record<string, unknown>>({});
  const [agents, setAgents] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    api.info().then(setInfo).catch(() => {});
    fetch("/api/providers").then(r => r.json()).then(d => setProviders(d.providers || [])).catch(() => {});
    fetch("/api/memory").then(r => r.json()).then(d => setMemStats(d.stats || {})).catch(() => {});
    api.agents().then(d => setAgents(d.agents || [])).catch(() => {});
  }, []);

  const refresh = () => {
    api.info().then(setInfo).catch(() => {});
    fetch("/api/providers").then(r => r.json()).then(d => setProviders(d.providers || [])).catch(() => {});
    fetch("/api/memory").then(r => r.json()).then(d => setMemStats(d.stats || {})).catch(() => {});
  };

  return (
    <div className="admin-panel">
      <div className="actions-bar">
        <h2>Admin Panel</h2>
        <button onClick={refresh} className="btn-secondary">Refresh</button>
      </div>

      <div className="detail-grid">
        <div className="detail-section">
          <h3>System</h3>
          <table className="kv-table">
            <tbody>
              <tr><td>Version</td><td>{info?.version as string || "?"}</td></tr>
              <tr><td>Tools</td><td>{info?.tools_count as number || "?"}</td></tr>
              <tr><td>GitHub</td><td className={(info?.deploy as Record<string,boolean>)?.github ? "g" : "r"}>{(info?.deploy as Record<string,boolean>)?.github ? "Configured" : "Not set"}</td></tr>
              <tr><td>Cloudflare</td><td className={(info?.deploy as Record<string,boolean>)?.cloudflare ? "g" : "r"}>{(info?.deploy as Record<string,boolean>)?.cloudflare ? "Configured" : "Not set"}</td></tr>
              <tr><td>Domain</td><td>{(info?.deploy as Record<string,string>)?.domain || "?"}</td></tr>
            </tbody>
          </table>
        </div>

        <div className="detail-section">
          <h3>Providers</h3>
          <table className="kv-table">
            <tbody>
              {providers.map((p) => (
                <tr key={p.name as string}>
                  <td>{p.name as string}</td>
                  <td className={p.configured ? "g" : "r"}>{p.configured ? "Configured" : "Missing"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="detail-section">
          <h3>Memory Store</h3>
          {Object.keys(memStats).length > 0 ? (
            <table className="kv-table">
              <tbody>
                {Object.entries(memStats as Record<string,number>).filter(([k]) => k !== "total").slice(0, 10).map(([k, v]) => (
                  <tr key={k}><td>{k}</td><td>{v} items</td></tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="dim">Empty (lazy init)</p>
          )}
        </div>

        <div className="detail-section">
          <h3>Agents ({agents.length})</h3>
          <table className="kv-table">
            <tbody>
              {agents.map((a) => (
                <tr key={a.name as string}>
                  <td>{a.name as string}</td>
                  <td className="dim">{a.current_model as string} via {a.current_provider as string}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="detail-section">
        <h3>API Endpoints</h3>
        <div className="endpoint-list">
          {[
            ["GET", "/health", "Health check"],
            ["GET", "/api/info", "System info"],
            ["GET/POST", "/api/projects", "List/Create projects"],
            ["POST", "/api/run", "Start pipeline run"],
            ["GET", "/api/agents", "List agents"],
            ["GET", "/api/tools", "List tools"],
            ["GET", "/api/memory", "Memory stats"],
            ["WS", "/ws", "Live agent events"],
            ["GET", "/docs", "Swagger API docs"],
          ].map(([method, path, desc]) => (
            <div key={path} className="endpoint-item">
              <span className="endpoint-method">{method}</span>
              <span className="endpoint-path">{path}</span>
              <span className="dim">{desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
