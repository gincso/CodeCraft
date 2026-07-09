from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from codecraft import __version__
from codecraft.config import settings
from codecraft.state.store import project_store
from codecraft.memory import get_memory

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CodeCraft API",
    description="Multi-agent AI-powered software development platform",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_runs: dict[str, Any] = {}
ws_clients: dict[str, WebSocket] = {}


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    mode: str = "pipeline"


class ProjectRun(BaseModel):
    project_path: str
    mode: str = "pipeline"


class ConfigUpdate(BaseModel):
    key: str
    value: str


class MemoryQuery(BaseModel):
    agent: str = ""
    query: str
    n_results: int = 5


@app.get("/health")
async def health():
    return {"status": "ok", "version": __version__, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/info")
async def system_info():
    from codecraft.llm import registry
    from codecraft.llm.models import AGENT_MODEL_MAP

    providers = []
    for name in registry.list_providers():
        try:
            registry.get_provider(name)
            key_configured = _check_key_configured(name)
            providers.append({"name": name, "available": True, "key_configured": key_configured})
        except Exception:
            providers.append({"name": name, "available": False, "key_configured": False})

    return {
        "version": __version__,
        "providers": providers,
        "agents": list(AGENT_MODEL_MAP.keys()),
        "tools_count": 14,
        "deploy": {
            "github": bool(settings.deploy.github_token),
            "vps": bool(settings.deploy.vps_host),
            "cloudflare": bool(settings.deploy.cloudflare_tunnel_token),
            "domain": settings.deploy.domain,
        },
    }


def _check_key_configured(name: str) -> bool:
    checks = {
        "openai": settings.llm.openai_api_key,
        "openrouter": settings.llm.openrouter_api_key,
        "groq": settings.llm.groq_api_key,
        "gemini": settings.llm.gemini_api_key,
        "ollama": settings.llm.ollama_host,
    }
    return bool(checks.get(name))


@app.get("/api/providers")
async def list_providers():
    from codecraft.llm import registry
    return {"providers": [{"name": n, "configured": _check_key_configured(n)} for n in registry.list_providers()]}


@app.get("/api/projects")
async def list_projects():
    projects = project_store.list_projects()
    for p in projects:
        p["_path"] = p.get("_path", "")
    return {"projects": projects}


@app.post("/api/projects")
async def create_project(body: ProjectCreate):
    manifest = project_store.create(body.name, body.description)
    return {"project": manifest, "path": str(project_store.base_dir / manifest["slug"])}


@app.get("/api/projects/{project_slug}")
async def get_project(project_slug: str):
    try:
        path = str(project_store.base_dir / project_slug)
        manifest = project_store.load(path)
        return {"project": manifest}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@app.delete("/api/projects/{project_slug}")
async def delete_project(project_slug: str):
    path = str(project_store.base_dir / project_slug)
    project_store.delete(path)
    return {"deleted": True}


@app.get("/api/projects/{project_slug}/export")
async def export_project(project_slug: str):
    path = str(project_store.base_dir / project_slug)
    try:
        export_path = project_store.export_project(path)
        return FileResponse(export_path, filename=f"{project_slug}.codecraft.tar.gz")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@app.post("/api/projects/import")
async def import_project(archive_path: str, output_dir: str = ""):
    try:
        manifest = project_store.import_project(archive_path, output_dir or None)
        return {"project": manifest}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/run")
async def start_run(body: ProjectRun):
    from codecraft.orchestrator import Orchestrator

    manifest = project_store.load(body.project_path)
    run_id = str(uuid.uuid4())

    orchestrator = Orchestrator(
        project_name=manifest.get("name", "unknown"),
        project_description=manifest.get("description", ""),
        workdir=body.project_path,
        mode=body.mode,
    )

    def handle_event(event: str, data: dict[str, Any]) -> None:
        broadcast_event(event, data)

    orchestrator.on_event(handle_event)

    active_runs[run_id] = orchestrator

    asyncio.create_task(_run_pipeline(run_id, orchestrator))

    return {
        "run_id": run_id,
        "project": manifest.get("name"),
        "mode": body.mode,
        "status": "running",
    }


@app.get("/api/run/{run_id}")
async def get_run_status(run_id: str):
    orchestrator = active_runs.get(run_id)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "status": orchestrator.phase.value,
        "artifacts": orchestrator.artifacts,
        "errors": orchestrator.errors[-10:],
        "agent_outputs": {k: v[:500] for k, v in orchestrator.agent_outputs.items()},
    }


@app.post("/api/run/{run_id}/cancel")
async def cancel_run(run_id: str):
    orchestrator = active_runs.get(run_id)
    if orchestrator:
        orchestrator.abort()
    return {"cancelled": True}


@app.get("/api/agents")
async def list_agents():
    from codecraft.llm.models import AGENT_MODEL_MAP, resolve_model_for_agent
    agents = []
    for name in AGENT_MODEL_MAP:
        model, provider = resolve_model_for_agent(name)
        agents.append({
            "name": name,
            "models": AGENT_MODEL_MAP[name],
            "current_model": model,
            "current_provider": provider,
        })
    return {"agents": agents}


@app.get("/api/tools")
async def list_tools():
    from codecraft.tools import ALL_TOOLS
    return {
        "tools": [
            {"name": n, "risk": t.risk if hasattr(t, "risk") else "unknown"}
            for n, t in ALL_TOOLS.items()
        ]
    }


@app.get("/api/memory")
async def memory_stats():
    memory = get_memory()
    return {"stats": memory.get_stats()}


@app.post("/api/memory/search")
async def memory_search(body: MemoryQuery):
    memory = get_memory()
    results = memory.recall(body.agent or "researcher", body.query, body.n_results)
    return {"results": results}


@app.post("/api/memory/clear")
async def memory_clear(agent: str = "", project: str = ""):
    memory = get_memory()
    if agent:
        memory.clear_agent_memory(agent)
        return {"cleared": f"agent:{agent}"}
    if project:
        deleted = memory.clear_project_memory(project)
        return {"cleared": deleted}
    return {"cleared": 0}


@app.post("/api/setup")
async def api_setup(body: ConfigUpdate):
    from codecraft.main import _read_env, _write_env

    env = _read_env()
    env[body.key] = body.value
    _write_env(env)
    return {"saved": True, "key": body.key}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = str(uuid.uuid4())
    ws_clients[client_id] = websocket

    try:
        await websocket.send_json({"type": "connected", "client_id": client_id, "version": __version__})

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "subscribe":
                await websocket.send_json({"type": "subscribed", "run_id": data.get("run_id", "")})
            elif msg_type == "approve":
                run_id = data.get("run_id", "")
                orc = active_runs.get(run_id)
                if orc and hasattr(orc, "_manager"):
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.pop(client_id, None)


def broadcast_event(event: str, data: dict[str, Any]) -> None:
    message = {"type": "event", "event": event, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()}
    disconnected = []
    for cid, ws in ws_clients.items():
        try:
            ws._send(message)  # fire and forget
        except Exception:
            disconnected.append(cid)
    for cid in disconnected:
        ws_clients.pop(cid, None)


async def _run_pipeline(run_id: str, orchestrator: Any) -> None:
    try:
        result = await orchestrator.run()
        broadcast_event("run_complete", {"run_id": run_id, "result": result})
    except Exception as e:
        broadcast_event("run_error", {"run_id": run_id, "error": str(e)})
    finally:
        active_runs.pop(run_id, None)


def create_app() -> FastAPI:
    webui_dist = Path(__file__).parent.parent.parent / "webui" / "dist"
    if webui_dist.exists():
        app.mount("/assets", StaticFiles(directory=webui_dist / "assets"), name="assets")
        app.mount("/", StaticFiles(directory=webui_dist, html=True), name="webui")

        @app.get("/manifest.json")
        async def manifest():
            return FileResponse(webui_dist / "manifest.json")

        @app.get("/icon-{size}.png")
        async def icon(size: int):
            path = webui_dist / f"icon-{size}.png"
            if path.exists():
                return FileResponse(path)
            return JSONResponse({"error": "not found"}, status_code=404)
    return app
