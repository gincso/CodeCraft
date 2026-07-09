import { useState } from "react";

interface Props {
  onSubmit: (name: string, desc: string, mode: string) => void;
  agents: Array<Record<string, unknown>>;
}

export default function ProjectSetup({ onSubmit, agents: _agents }: Props) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [mode, setMode] = useState("pipeline");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!desc.trim()) return;
    onSubmit(name || desc.split(" ").slice(0, 2).join("-").toLowerCase(), desc, mode);
  };

  return (
    <div className="setup-page">
      <h2>New Project</h2>
      <form onSubmit={handleSubmit}>
        <label>
          Project Name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-awesome-app" />
        </label>
        <label>
          What do you want to build?
          <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={4} placeholder="Describe your project idea in detail... CodeCraft agents will research, plan, architect, develop, test, and deploy it." autoFocus />
        </label>
        <label>
          Mode
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="pipeline">Pipeline (sequential phases)</option>
            <option value="dynamic">Dynamic (AI-coordinated)</option>
          </select>
        </label>
        <div className="agent-preview">
          <span>Agents that will work on this:</span>
          <div className="agent-tags">
            {["researcher", "planner", "architect", "developer", "reviewer", "tester", "devops", "security"].map((a) => (
              <span key={a} className="agent-tag">{a}</span>
            ))}
          </div>
        </div>
        <button type="submit" className="btn-primary">Start Building</button>
      </form>
    </div>
  );
}
