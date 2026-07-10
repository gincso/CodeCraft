import { useState, useEffect } from "react";
import { api } from "../lib/api";

interface Props {
  project: Record<string, unknown>;
  onBack: () => void;
  onRun: (path: string) => void;
}

interface ProjectFile {
  name: string;
  size: number;
  content: string;
}

export default function ProjectDetail({ project, onBack, onRun }: Props) {
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const projectPath = project._path as string || "";

  useEffect(() => {
    if (projectPath) {
      api.projects.get(projectPath).then((d) => {
        setFiles((d.project?.files as ProjectFile[]) || []);
        setLoading(false);
      }).catch(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [projectPath]);

  const artifacts = (project.artifacts as Record<string, string>) || {};
  const phases = (project.phases_completed as string[]) || [];
  const selectedContent = files.find((f) => f.name === selectedFile)?.content || "";

  return (
    <div className="project-detail">
      <div className="detail-header">
        <button onClick={onBack} className="btn-secondary">← Back</button>
        <h2>{project.name as string}</h2>
        <span className={`status ${project.status}`}>{project.status as string}</span>
        <button onClick={() => onRun(projectPath)} className="btn-primary">Run Pipeline</button>
      </div>

      <p className="detail-desc">{project.description as string}</p>

      <div className="detail-grid">
        <div className="detail-section">
          <h3>Phases ({phases.length}/8)</h3>
          <div className="phases-list">
            {["research", "planning", "architecture", "development", "review", "testing", "deployment", "security"].map((p) => {
              const done = phases.includes(p);
              return (
                <div key={p} className={`phase-item ${done ? "done" : ""}`}>
                  <span className="dot" style={{ background: done ? "#3fb950" : "#30363d" }} />
                  <span>{p}</span>
                  {artifacts[p] && <a href="#" onClick={(e) => { e.preventDefault(); setSelectedFile(artifacts[p].split("/").pop() || ""); }} className="artifact-link">view</a>}
                </div>
              );
            })}
          </div>
        </div>

        <div className="detail-section">
          <h3>Files ({files.length})</h3>
          {loading ? (
            <p className="dim">Loading...</p>
          ) : files.length === 0 ? (
            <p className="dim">No files yet. Run the pipeline to generate code.</p>
          ) : (
            <div className="files-list">
              {files.map((f) => (
                <div
                  key={f.name}
                  className={`file-item ${selectedFile === f.name ? "selected" : ""}`}
                  onClick={() => setSelectedFile(f.name)}
                >
                  <span>{f.name}</span>
                  <span className="dim">{f.size}b</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {selectedContent && (
        <div className="detail-section">
          <h3>File: {selectedFile}</h3>
          <pre className="code-preview">{selectedContent}</pre>
        </div>
      )}

      <div className="detail-section">
        <h3>Errors</h3>
        {((project.errors as string[]) || []).length > 0 ? (
          <ul>
            {(project.errors as string[]).map((e, i) => (
              <li key={i} className="error-item">{e.slice(0, 200)}</li>
            ))}
          </ul>
        ) : (
          <p className="dim">No errors</p>
        )}
      </div>
    </div>
  );
}
