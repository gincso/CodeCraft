import { useState, useEffect } from "react";
import { api } from "./lib/api";
import { useWebSocket } from "./hooks/useWebSocket";
import type { WSEvent } from "./hooks/useWebSocket";
import Dashboard from "./components/Dashboard";
import ProjectSetup from "./components/ProjectSetup";
import ProjectDetail from "./components/ProjectDetail";
import AgentTheater from "./components/AgentTheater";
import AdminPanel from "./components/AdminPanel";
import ConversationView from "./components/ConversationView";
import "./App.css";

type Page = "dashboard" | "setup" | "run" | "detail" | "admin" | "conversations";

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [projects, setProjects] = useState<Array<Record<string, unknown>>>([]);
  const [activeRun, setActiveRun] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<Record<string, unknown> | null>(null);
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
        api.projects.list().then((d) => setProjects(d.projects || [])).catch(() => {});
      }
    });
  }, [on]);

  const handleCreateProject = async (name: string, desc: string, mode: string) => {
    setError("");
    try {
      const result = await api.projects.create({ name, description: desc, mode });
      const path = (result.project?._path || result.path) as string;

      const runResult = await api.run.start(path, mode);
      setActiveRun(runResult.run_id as string);
      setRunEvents([]);
      setPage("run");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  };

  const handleSelectProject = (project: Record<string, unknown>) => {
    setSelectedProject(project);
    setPage("detail");
  };

  const handleRunProject = async (path: string) => {
    try {
      const result = await api.run.start(path, "pipeline");
      setActiveRun(result.run_id as string);
      setRunEvents([]);
      setPage("run");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start run");
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
        <h1 onClick={() => { setPage("dashboard"); setSelectedProject(null); }}>CodeCraft</h1>
        <nav>
          <button className={page === "dashboard" ? "active" : ""} onClick={() => { setPage("dashboard"); setSelectedProject(null); }}>Projects</button>
          <button className={page === "setup" ? "active" : ""} onClick={() => setPage("setup")}>New</button>
          <button className={page === "admin" ? "active" : ""} onClick={() => setPage("admin")}>Admin</button>
          <button className={page === "conversations" ? "active" : ""} onClick={() => setPage("conversations")}>Conversations</button>
          {activeRun && <button className="active" onClick={() => setPage("run")}>Live Run</button>}
          <span className={`ws-status ${connected ? "connected" : "disconnected"}`}>
            {connected ? "connected" : "reconnecting"}
          </span>
        </nav>
      </header>

      <main>
        {error && <div className="error-banner" onClick={() => setError("")}>{error} ✕</div>}

        {page === "dashboard" && (
          <Dashboard
            projects={projects}
            agents={agents}
            onNew={() => setPage("setup")}
            onRefresh={() => api.projects.list().then((d) => setProjects(d.projects || []))}
            onSelect={handleSelectProject}
          />
        )}

        {page === "detail" && selectedProject && (
          <ProjectDetail
            project={selectedProject}
            onBack={() => setPage("dashboard")}
            onRun={handleRunProject}
          />
        )}

        {page === "setup" && (
          <ProjectSetup onSubmit={handleCreateProject} agents={agents} />
        )}

        {page === "run" && activeRun && (
          <AgentTheater runEvents={runEvents} onCancel={handleCancel} />
        )}

        {page === "admin" && <AdminPanel />}

        {page === "conversations" && <ConversationView />}
      </main>
    </div>
  );
}

export default App;
