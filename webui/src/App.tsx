import { useState, useEffect } from "react";
import { api } from "./lib/api";
import { useWebSocket } from "./hooks/useWebSocket";
import type { WSEvent } from "./hooks/useWebSocket";
import Dashboard from "./components/Dashboard";
import ProjectSetup from "./components/ProjectSetup";
import AgentTheater from "./components/AgentTheater";
import "./App.css";

type Page = "dashboard" | "setup" | "run";

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [projects, setProjects] = useState<Array<Record<string, unknown>>>([]);
  const [activeRun, setActiveRun] = useState<string | null>(null);
  const { connected, on } = useWebSocket();
  const [runEvents, setRunEvents] = useState<Array<WSEvent>>([]);
  const [agents, setAgents] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.projects.list().then((d) => setProjects(d.projects || [])).catch(() => {});
    api.agents().then((d) => setAgents(d.agents || [])).catch(() => {});
  }, []);

  useEffect(() => {
    return on((e) => {
      if (e.event === "agent_start" || e.event === "agent_complete" || e.event === "agent_error") {
        setRunEvents((p: WSEvent[]) => [e, ...p].slice(0, 100));
      }
      if (e.event === "run_complete" || e.event === "run_error") {
        setActiveRun(null);
      }
    });
  }, [on]);

  const handleCreateProject = async (name: string, desc: string, mode: string) => {
    setError("");
    try {
      const result = await api.projects.create({ name, description: desc, mode });
      const path = (result.project?._path || result.path) as string;

      api.projects.list().then((d) => setProjects(d.projects || []));

      const runResult = await api.run.start(path, mode);
      setActiveRun(runResult.run_id as string);
      setRunEvents([]);
      setPage("run");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create project");
    }
  };

  const handleCancel = async () => {
    if (activeRun) {
      await api.run.cancel(activeRun);
      setActiveRun(null);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1 onClick={() => setPage("dashboard")}>CodeCraft</h1>
        <nav>
          <button className={page === "dashboard" ? "active" : ""} onClick={() => setPage("dashboard")}>Projects</button>
          <button className={page === "setup" ? "active" : ""} onClick={() => setPage("setup")}>New</button>
          {activeRun && <button className="active" onClick={() => setPage("run")}>Live Run</button>}
          <span className={`ws-status ${connected ? "connected" : "disconnected"}`}>
            {connected ? "connected" : "reconnecting"}
          </span>
        </nav>
      </header>

      <main>
        {error && <div className="error-banner">{error}</div>}

        {page === "dashboard" && (
          <Dashboard projects={projects} agents={agents} onNew={() => setPage("setup")} onRefresh={() => api.projects.list().then((d) => setProjects(d.projects || []))} />
        )}

        {page === "setup" && (
          <ProjectSetup onSubmit={handleCreateProject} agents={agents} />
        )}

        {page === "run" && activeRun && (
          <AgentTheater runEvents={runEvents} onCancel={handleCancel} />
        )}
      </main>
    </div>
  );
}

export default App;
