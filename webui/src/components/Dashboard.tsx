interface Props {
  projects: Array<Record<string, unknown>>;
  agents: Array<Record<string, unknown>>;
  onNew: () => void;
  onRefresh: () => void;
}

export default function Dashboard({ projects, agents, onNew, onRefresh }: Props) {
  return (
    <div className="dashboard">
      <div className="actions-bar">
        <h2>Projects ({projects.length})</h2>
        <div>
          <button onClick={onRefresh} className="btn-secondary">Refresh</button>
          <button onClick={onNew} className="btn-primary">+ New Project</button>
        </div>
      </div>

      {projects.length === 0 ? (
        <div className="empty-state">
          <p>No projects yet.</p>
          <button onClick={onNew} className="btn-primary">Create Your First Project</button>
        </div>
      ) : (
        <div className="project-grid">
          {projects.map((p) => (
            <div key={p._path as string} className="project-card">
              <h3>{p.name as string}</h3>
              <span className={`status ${p.status}`}>{p.status as string}</span>
              <p className="desc">{(p.description as string)?.slice(0, 100) || ""}</p>
              <div className="phases">
                {((p.phases_completed as string[]) || []).slice(0, 5).map((ph: string) => (
                  <span key={ph} className="phase-badge">{ph}</span>
                ))}
              </div>
              <div className="card-meta">
                <span>{(p.updated_at as string)?.slice(0, 10) || ""}</span>
                <span>{p.mode as string || "pipeline"}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <h2 style={{ marginTop: 32 }}>Agents ({agents.length})</h2>
      <div className="agent-grid">
        {agents.map((a) => (
          <div key={a.name as string} className="agent-card">
            <strong>{a.name as string}</strong>
            <span className="dim">{a.current_model as string}</span>
          </div>
        ))}
        {agents.length === 0 && <p className="dim">Loading agents...</p>}
      </div>
    </div>
  );
}
