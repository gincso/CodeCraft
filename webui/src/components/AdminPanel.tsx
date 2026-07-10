import { useState, useEffect } from "react";
import { api } from "../lib/api";

export default function AdminPanel() {
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);
  const [providers, setProviders] = useState<Array<Record<string, unknown>>>([]);
  const [memStats, setMemStats] = useState<Record<string, unknown>>({});
  const [agents, setAgents] = useState<Array<Record<string, unknown>>>([]);
  const [config, setConfig] = useState<Record<string, string>>({});
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saveMsg, setSaveMsg] = useState("");

  const loadAll = () => {
    api.info().then(setInfo).catch(() => {});
    fetch("/api/providers").then(r => r.json()).then(d => setProviders(d.providers || [])).catch(() => {});
    fetch("/api/memory").then(r => r.json()).then(d => setMemStats(d.stats || {})).catch(() => {});
    api.agents().then(d => setAgents(d.agents || [])).catch(() => {});
    fetch("/api/admin/config").then(r => r.json()).then(d => setConfig(d.config || {})).catch(() => {});
  };

  useEffect(() => { loadAll(); }, []);

  const handleSave = async () => {
    if (!editingKey) return;
    try {
      await fetch("/api/admin/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: editingKey, value: editValue }),
      });
      setConfig(prev => ({ ...prev, [editingKey]: editValue }));
      setSaveMsg(`Saved ${editingKey}`);
      setEditingKey(null);
      setTimeout(() => setSaveMsg(""), 3000);
    } catch {
      setSaveMsg("Save failed");
    }
  };

  const handleRevert = async () => {
    if (!confirm("Revert all config to defaults?")) return;
    try {
      const res = await fetch("/api/admin/config/revert", { method: "POST" });
      const data = await res.json();
      setSaveMsg(`Reverted ${data.keys?.length || 0} keys`);
      loadAll();
      setTimeout(() => setSaveMsg(""), 3000);
    } catch {
      setSaveMsg("Revert failed");
    }
  };

  const startEdit = (key: string, value: string) => {
    setEditingKey(key);
    setEditValue(value);
  };

  const configGroups = {
    "LLM Provider": Object.entries(config).filter(([k]) => k.startsWith("CODECRAFT_LLM_") && !k.includes("API_KEY")),
    "API Keys": Object.entries(config).filter(([k]) => k.includes("API_KEY") || k.includes("TOKEN")),
    "Deployment": Object.entries(config).filter(([k]) => k.startsWith("CODECRAFT_DEPLOY_") && !k.includes("TOKEN")),
    "Other": Object.entries(config).filter(([k]) => !k.startsWith("CODECRAFT_LLM_") && !k.startsWith("CODECRAFT_DEPLOY_") && !k.includes("API_KEY") && !k.includes("TOKEN")),
  };

  return (
    <div className="admin-panel">
      <div className="actions-bar">
        <h2>Admin Panel</h2>
        <div style={{ display: "flex", gap: 8 }}>
          {saveMsg && <span className="save-msg">{saveMsg}</span>}
          <button onClick={handleRevert} className="btn-danger">Revert to Default</button>
          <button onClick={loadAll} className="btn-secondary">Refresh</button>
        </div>
      </div>

      <div className="detail-section">
        <h3>Configuration</h3>
        {Object.entries(configGroups).map(([group, entries]) => (
          entries.length > 0 && (
            <div key={group} style={{ marginBottom: 16 }}>
              <h4 style={{ fontSize: "0.85rem", color: "#58a6ff", marginBottom: 8 }}>{group}</h4>
              <table className="kv-table">
                <tbody>
                  {entries.map(([key, value]) => (
                    <tr key={key}>
                      <td style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>{key}</td>
                      <td>
                        {editingKey === key ? (
                          <div style={{ display: "flex", gap: 4 }}>
                            <input
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              style={{ flex: 1, padding: "2px 6px", fontSize: "0.8rem" }}
                              onKeyDown={(e) => e.key === "Enter" && handleSave()}
                            />
                            <button onClick={handleSave} className="btn-primary" style={{ padding: "2px 8px", fontSize: "0.75rem" }}>Save</button>
                            <button onClick={() => setEditingKey(null)} className="btn-secondary" style={{ padding: "2px 8px", fontSize: "0.75rem" }}>Cancel</button>
                          </div>
                        ) : (
                          <div
                            onClick={() => startEdit(key, value)}
                            style={{ cursor: "pointer", padding: "2px 0" }}
                            className="dim"
                          >
                            {key.includes("KEY") || key.includes("TOKEN") ? "••••••••" : value || "(empty)"}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ))}
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
            ["GET", "/api/admin/config", "Read config"],
            ["POST", "/api/admin/config", "Update config"],
            ["POST", "/api/admin/config/revert", "Revert to defaults"],
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
