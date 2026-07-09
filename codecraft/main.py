from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.text import Text

from codecraft import __version__
from codecraft.config import settings
from codecraft.orchestrator import Orchestrator, Phase, ThinkTank
from codecraft.llm import create_fallback_provider
from codecraft.state.store import project_store
from codecraft.memory import get_memory

console = Console()
app = typer.Typer(
    name="codecraft",
    help="Multi-agent AI-powered software development platform — from idea to deployed product.",
    no_args_is_help=True,
)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def get_default_tools(workdir: str) -> list:
    from codecraft.tools.filesystem import ReadFileTool, WriteFileTool, ListDirectoryTool, SearchFilesTool, GrepTool
    from codecraft.tools.shell import ShellTool
    from codecraft.tools.web_search import WebSearchTool, WebFetchTool
    from codecraft.tools.code_runner import CodeRunnerTool
    from codecraft.tools.git import GitTool
    return [
        ReadFileTool(workdir=workdir),
        WriteFileTool(workdir=workdir),
        ListDirectoryTool(workdir=workdir),
        SearchFilesTool(workdir=workdir),
        GrepTool(workdir=workdir),
        ShellTool(workdir=workdir),
        WebSearchTool(workdir=workdir),
        WebFetchTool(workdir=workdir),
        CodeRunnerTool(workdir=workdir),
        GitTool(workdir=workdir),
    ]


@app.command()
def version() -> None:
    """Show CodeCraft version."""
    console.print(f"[bold cyan]CodeCraft[/] v{__version__}")


@app.command()
def init(
    project_description: str = typer.Argument(..., help="Description of the project to build"),
    name: str = typer.Option(None, "--name", "-n", help="Project name"),
    mode: str = typer.Option("pipeline", "--mode", "-m", help="Execution mode: pipeline or dynamic"),
    workdir: str = typer.Option(None, "--workdir", "-w", help="Working directory for the project"),
    skip_deps: bool = typer.Option(False, "--skip-deps", help="Skip dependency installation check"),
) -> None:
    """Initialize a new project and start the build pipeline."""
    from datetime import datetime, timezone
    from rich.layout import Layout
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn

    project_name = name or project_description.split()[0].lower().replace(" ", "-")[:40]
    project_workdir = workdir or str(Path.cwd() / "projects" / project_name)
    Path(project_workdir).mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit(
        f"[bold cyan]🚀 CodeCraft[/] [dim]v{__version__}[/]\n"
        f"[bold]Project:[/] [white]{project_name}[/]\n"
        f"[bold]Goal:[/] {project_description}\n"
        f"[bold]Mode:[/] [yellow]{mode}[/]\n"
        f"[bold]Workdir:[/] [dim]{project_workdir}[/]",
        title="[bold]New Project[/]",
        border_style="cyan",
    ))

    orchestrator = Orchestrator(
        project_name=project_name,
        project_description=project_description,
        workdir=project_workdir,
        mode=mode,
    )

    agent_status: dict[str, str] = {}
    agent_results: dict[str, str] = {}
    current_agent = "initializing"
    events: list[str] = []

    def handle_event(event: str, data: dict) -> None:
        nonlocal current_agent
        if event == "agent_start":
            agent_name = data.get("agent", "unknown")
            current_agent = agent_name
            agent_status[agent_name] = "running"
            model_info = f"({data.get('model', '?')} via {data.get('provider', '?')})"
            events.append(f"[cyan]▶[/] {agent_name} {model_info}")
        elif event == "agent_complete":
            agent_name = data.get("agent", "unknown")
            agent_status[agent_name] = "done"
            result = data.get("output", "")
            if result:
                agent_results[agent_name] = result[:200]
            events.append(f"[green]✅[/] {agent_name} complete")
        elif event == "agent_error":
            agent_name = data.get("agent", "unknown")
            agent_status[agent_name] = "error"
            events.append(f"[red]❌[/] {agent_name}: {data.get('error', '')[:100]}")
        elif event == "pipeline_complete":
            events.append(f"[bold green]🏁 Pipeline {data.get('status', 'done')}[/]")

    orchestrator.on_event(handle_event)

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )
    phase_task = progress.add_task("[cyan]Pipeline Progress", total=8)

    def render_layout() -> Panel:
        lines = ["[bold cyan]Agent Status[/]", "─" * 40]
        for agent_name, status in agent_status.items():
            icon = {"running": "[yellow]◉[/]", "done": "[green]◉[/]", "error": "[red]◉[/]"}.get(status, "[dim]○[/]")
            lines.append(f"  {icon} [bold]{agent_name}[/]: {status}")
        if not agent_status:
            lines.append("  [dim]Waiting to start...[/]")
        lines.append("")
        lines.append("[bold]Recent Events[/]")
        lines.append("─" * 40)
        for evt in events[-6:]:
            lines.append(f"  {evt}")
        return Panel("\n".join(lines), title="[bold]Live Agent Theater[/]", border_style="cyan")

    with Live(render_layout(), refresh_per_second=4, console=console) as live:
        def update_progress():
            completed = sum(1 for s in agent_status.values() if s == "done")
            progress.update(phase_task, completed=completed)
            live.update(render_layout())

        async def run_with_progress():
            orchestrator.on_event(lambda e, d: update_progress())
            return await orchestrator.run()

        try:
            result = asyncio.run(run_with_progress())
        except KeyboardInterrupt:
            orchestrator.abort()
            console.print("\n[yellow]⚠ Pipeline aborted by user[/]")
            return

    console.print()
    console.print(Panel.fit(
        f"[bold]Status:[/] [{'green' if result['status'] == 'complete' else 'red'}]{result['status']}[/]\n"
        f"[bold]Artifacts:[/] {len(result['artifacts'])}\n"
        f"[bold]Errors:[/] {len(result['errors'])}\n"
        f"[bold]Directory:[/] [dim]{project_workdir}[/]",
        title="[bold]Pipeline Complete[/]",
        border_style="green" if result["status"] == "complete" else "red",
    ))

    if result["errors"]:
        console.print("\n[red bold]Errors:[/]")
        for err in result["errors"]:
            console.print(f"  [red]•[/] {err}")

    console.print("\n[bold]Artifacts:[/]")
    for phase, path in result["artifacts"].items():
        console.print(f"  [cyan]📄[/] {phase}: [dim]{path}[/]")

    if result["status"] == "complete":
        console.print(f"\n[bold green]✨ Project ready at: {project_workdir}[/]")
        console.print(f"[dim]Next: cd {project_workdir}  &&  explore the generated code[/]")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload", "-r"),
) -> None:
    """Start the CodeCraft API server."""
    try:
        import uvicorn
        from codecraft.api.server import create_app

        console.print(f"[cyan]Starting CodeCraft API on {host}:{port}[/]")
        app = create_app()
        uvicorn.run(app, host=host, port=port, reload=reload)
    except ImportError:
        console.print("[red]API dependencies not installed. Run: pip install uvicorn[/]")


@app.command()
def list_providers() -> None:
    """List available LLM providers and their status."""
    from codecraft.llm import registry

    table = Table(title="LLM Providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Status", style="green")

    for name in registry.list_providers():
        try:
            provider = registry.get_provider(name)
            table.add_row(name, "available")
        except Exception as e:
            table.add_row(name, f"[red]unavailable: {e}")

    console.print(table)


@app.command()
def config_show() -> None:
    """Show current configuration."""
    config_data = {
        "llm": {
            "provider": settings.llm.provider,
            "model": settings.llm.model,
            "fallback_chain": settings.llm.fallback_chain,
            "openai_configured": bool(settings.llm.openai_api_key),
            "openrouter_configured": bool(settings.llm.openrouter_api_key),
            "groq_configured": bool(settings.llm.groq_api_key),
            "gemini_configured": bool(settings.llm.gemini_api_key),
            "ollama_host": settings.llm.ollama_host,
        },
        "deploy": {
            "domain": settings.deploy.domain,
            "vps_configured": bool(settings.deploy.vps_host),
            "github_configured": bool(settings.deploy.github_token),
            "cloudflare_configured": bool(settings.deploy.cloudflare_tunnel_token),
        },
        "core": {
            "data_dir": settings.data_dir,
            "max_concurrent_agents": settings.max_concurrent_agents,
            "sandbox_enabled": settings.sandbox_enabled,
            "require_tool_approval": settings.require_tool_approval,
        },
    }
    console.print_json(json.dumps(config_data, indent=2))


ENV_PATH = Path.cwd() / ".env"


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip("\"'")
    return env


def _write_env(env: dict[str, str]) -> None:
    lines = [
        "# CodeCraft Configuration - Generated by codecraft setup",
        "",
        "# LLM Providers",
        f"CODECRAFT_LLM_PROVIDER={env.get('CODECRAFT_LLM_PROVIDER', 'openai')}",
        f"CODECRAFT_LLM_MODEL={env.get('CODECRAFT_LLM_MODEL', 'gpt-4o')}",
        f"CODECRAFT_LLM_OPENAI_API_KEY={env.get('CODECRAFT_LLM_OPENAI_API_KEY', '')}",
        f"CODECRAFT_LLM_OPENAI_BASE_URL={env.get('CODECRAFT_LLM_OPENAI_BASE_URL', '')}",
        f"CODECRAFT_LLM_OPENROUTER_API_KEY={env.get('CODECRAFT_LLM_OPENROUTER_API_KEY', '')}",
        f"CODECRAFT_LLM_GROQ_API_KEY={env.get('CODECRAFT_LLM_GROQ_API_KEY', '')}",
        f"CODECRAFT_LLM_GEMINI_API_KEY={env.get('CODECRAFT_LLM_GEMINI_API_KEY', '')}",
        f"CODECRAFT_LLM_OLLAMA_HOST={env.get('CODECRAFT_LLM_OLLAMA_HOST', 'http://localhost:11434')}",
        f"CODECRAFT_LLM_FALLBACK_CHAIN={env.get('CODECRAFT_LLM_FALLBACK_CHAIN', 'openai,openrouter,groq,ollama')}",
        "",
        "# Google Cloud",
        f"CODECRAFT_GOOGLE_PROJECT_ID={env.get('CODECRAFT_GOOGLE_PROJECT_ID', '')}",
        f"CODECRAFT_GOOGLE_REGION={env.get('CODECRAFT_GOOGLE_REGION', 'us-central1')}",
        "",
        "# Deployment",
        f"CODECRAFT_DEPLOY_VPS_HOST={env.get('CODECRAFT_DEPLOY_VPS_HOST', '')}",
        f"CODECRAFT_DEPLOY_VPS_USER={env.get('CODECRAFT_DEPLOY_VPS_USER', 'root')}",
        f"CODECRAFT_DEPLOY_VPS_SSH_KEY={env.get('CODECRAFT_DEPLOY_VPS_SSH_KEY', '')}",
        f"CODECRAFT_DEPLOY_VPS_PORT={env.get('CODECRAFT_DEPLOY_VPS_PORT', '22')}",
        f"CODECRAFT_DEPLOY_DOMAIN={env.get('CODECRAFT_DEPLOY_DOMAIN', 'gincso.tech')}",
        f"CODECRAFT_DEPLOY_GITHUB_TOKEN={env.get('CODECRAFT_DEPLOY_GITHUB_TOKEN', '')}",
        f"CODECRAFT_DEPLOY_GITHUB_USER={env.get('CODECRAFT_DEPLOY_GITHUB_USER', '')}",
        f"CODECRAFT_DEPLOY_CLOUDFLARE_TUNNEL_TOKEN={env.get('CODECRAFT_DEPLOY_CLOUDFLARE_TUNNEL_TOKEN', '')}",
        f"CODECRAFT_DEPLOY_CLOUDFLARE_ZONE_ID={env.get('CODECRAFT_DEPLOY_CLOUDFLARE_ZONE_ID', '')}",
    ]
    ENV_PATH.write_text("\n".join(lines) + "\n")
    ENV_PATH.chmod(0o600)


async def _validate_openai(api_key: str) -> tuple[bool, str]:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as c:
            resp = await c.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                count = len(data.get("data", []))
                return True, f"valid ({count} models available)"
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


async def _validate_openrouter(api_key: str) -> tuple[bool, str]:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as c:
            resp = await c.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                count = len(data.get("data", []))
                return True, f"valid ({count} models available)"
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


async def _validate_groq(api_key: str) -> tuple[bool, str]:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as c:
            resp = await c.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                count = len(data.get("data", []))
                return True, f"valid ({count} models available)"
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


async def _validate_gemini(api_key: str) -> tuple[bool, str]:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as c:
            resp = await c.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])
                          if "generateContent" in m.get("supportedGenerationMethods", [])]
                return True, f"valid ({len(models)} models available)"
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


async def _validate_github(token: str) -> tuple[bool, str]:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as c:
            resp = await c.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if resp.status_code == 200:
                user = resp.json().get("login", "unknown")
                return True, f"valid (user: {user})"
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


@app.command()
def setup() -> None:
    """Interactive setup wizard for API keys and deployment configuration."""
    console.print(Panel.fit(
        "[bold cyan]CodeCraft Setup Wizard[/]\n"
        "Configure your LLM providers and deployment settings.\n"
        "Keys are stored in [dim].env[/] and never logged.",
        border_style="cyan",
    ))

    env = _read_env()

    console.print("\n[bold]LLM Provider Keys[/]")
    console.print("─" * 50)

    providers = [
        ("openai", "OpenAI", "https://platform.openai.com/api-keys", _validate_openai),
        ("openrouter", "OpenRouter", "https://openrouter.ai/keys", _validate_openrouter),
        ("groq", "Groq (free tier)", "https://console.groq.com/keys", _validate_groq),
        ("gemini", "Google Gemini ($300 GCP credits)", "https://aistudio.google.com/apikey", _validate_gemini),
    ]

    for key, label, url, validator in providers:
        env_key = f"CODECRAFT_LLM_{key.upper()}_API_KEY"
        current = env.get(env_key, "")

        status = "[red]not set[/]" if not current else "[dim]configured[/]"

        console.print(f"\n[bold white]{label}[/] ({url})")
        console.print(f"  Status: {status}")

        if current:
            if Confirm.ask("  Keep existing key?", default=True):
                continue

        new_key = Prompt.ask(
            f"  Enter {label} API key",
            default="",
            password=True,
        )

        if new_key:
            env[env_key] = new_key
            console.print("  Validating...", end=" ")
            ok, msg = asyncio.run(validator(new_key))
            if ok:
                console.print(f"[green]{msg}[/]")
            else:
                console.print(f"[red]invalid: {msg}[/]")
                if not Confirm.ask("  Save anyway?", default=False):
                    env[env_key] = ""
                    continue
            env[env_key] = new_key

    console.print("\n[bold]Deployment Settings[/]")
    console.print("─" * 50)

    console.print("\n[bold white]GitHub[/] (https://github.com/settings/tokens)")
    current_gh = env.get("CODECRAFT_DEPLOY_GITHUB_TOKEN", "")
    if current_gh:
        console.print(f"  Status: [dim]configured[/]")
    if not current_gh or not Confirm.ask("  Keep existing GitHub token?", default=bool(current_gh)):
        gh_token = Prompt.ask("  GitHub personal access token", default="", password=True)
        if gh_token:
            console.print("  Validating...", end=" ")
            ok, msg = asyncio.run(_validate_github(gh_token))
            if ok:
                console.print(f"[green]{msg}[/]")
                env["CODECRAFT_DEPLOY_GITHUB_TOKEN"] = gh_token
            else:
                console.print(f"[red]{msg}[/]")

    gh_user = Prompt.ask("  GitHub username", default=env.get("CODECRAFT_DEPLOY_GITHUB_USER", ""))
    if gh_user:
        env["CODECRAFT_DEPLOY_GITHUB_USER"] = gh_user

    console.print("\n[bold white]Google Cloud[/] ($300 free credits)")
    gcp_project = Prompt.ask(
        "  GCP Project ID",
        default=env.get("CODECRAFT_GOOGLE_PROJECT_ID", ""),
    )
    if gcp_project:
        env["CODECRAFT_GOOGLE_PROJECT_ID"] = gcp_project
    gcp_region = Prompt.ask(
        "  GCP Region",
        default=env.get("CODECRAFT_GOOGLE_REGION", "us-central1"),
    )
    env["CODECRAFT_GOOGLE_REGION"] = gcp_region

    console.print("\n[bold white]Domain[/]")
    domain = Prompt.ask("  Domain", default=env.get("CODECRAFT_DEPLOY_DOMAIN", "gincso.tech"))
    env["CODECRAFT_DEPLOY_DOMAIN"] = domain

    console.print("\n[bold white]Hostinger VPS[/]")
    vps_host = Prompt.ask("  VPS host/IP", default=env.get("CODECRAFT_DEPLOY_VPS_HOST", ""))
    env["CODECRAFT_DEPLOY_VPS_HOST"] = vps_host
    vps_user = Prompt.ask("  VPS user", default=env.get("CODECRAFT_DEPLOY_VPS_USER", "root"))
    env["CODECRAFT_DEPLOY_VPS_USER"] = vps_user
    vps_key = Prompt.ask(
        "  SSH key path (e.g. ~/.ssh/id_ed25519)",
        default=env.get("CODECRAFT_DEPLOY_VPS_SSH_KEY", ""),
    )
    env["CODECRAFT_DEPLOY_VPS_SSH_KEY"] = vps_key

    console.print("\n[bold white]Cloudflare Tunnel[/]")
    cf_token = Prompt.ask(
        "  Cloudflare tunnel token",
        default=env.get("CODECRAFT_DEPLOY_CLOUDFLARE_TUNNEL_TOKEN", ""),
        password=True,
    )
    env["CODECRAFT_DEPLOY_CLOUDFLARE_TUNNEL_TOKEN"] = cf_token
    cf_zone = Prompt.ask(
        "  Cloudflare zone ID",
        default=env.get("CODECRAFT_DEPLOY_CLOUDFLARE_ZONE_ID", ""),
    )
    env["CODECRAFT_DEPLOY_CLOUDFLARE_ZONE_ID"] = cf_zone

    console.print("\n[bold]Provider Selection[/]")
    console.print("─" * 50)
    primary = Prompt.ask(
        "  Default LLM provider",
        choices=["openai", "openrouter", "groq", "gemini", "ollama"],
        default="openai",
    )
    env["CODECRAFT_LLM_PROVIDER"] = primary

    chain_input = Prompt.ask(
        "  Fallback chain (comma-separated order)",
        default="openai,openrouter,groq,ollama",
    )
    env["CODECRAFT_LLM_FALLBACK_CHAIN"] = chain_input

    _write_env(env)

    console.print("\n[green bold]Configuration saved to .env[/]")
    console.print("[dim]Permissions set to 600 (owner read/write only)[/]")

    console.print("\n[bold]Summary:[/]")
    table = Table()
    table.add_column("Provider", style="cyan")
    table.add_column("Status", style="green")
    for key, label, url, _ in providers:
        env_key = f"CODECRAFT_LLM_{key.upper()}_API_KEY"
        configured = bool(env.get(env_key, ""))
        table.add_row(
            label,
            "[green]configured[/]" if configured else "[red]not configured[/]",
        )
    for name, env_key in [
        ("GitHub", "CODECRAFT_DEPLOY_GITHUB_TOKEN"),
        ("VPS", "CODECRAFT_DEPLOY_VPS_HOST"),
        ("Cloudflare", "CODECRAFT_DEPLOY_CLOUDFLARE_TUNNEL_TOKEN"),
        ("Google Cloud", "CODECRAFT_GOOGLE_PROJECT_ID"),
    ]:
        configured = bool(env.get(env_key, ""))
        table.add_row(
            name,
            "[green]configured[/]" if configured else "[dim]not configured[/]",
        )
    console.print(table)


@app.command()
def validate_keys() -> None:
    """Validate all configured API keys."""
    env = _read_env()

    console.print("[bold]Validating API Keys...[/]\n")

    checks: list[tuple[str, str]] = []

    if env.get("CODECRAFT_LLM_OPENAI_API_KEY"):
        checks.append(("OpenAI", env["CODECRAFT_LLM_OPENAI_API_KEY"]))
    if env.get("CODECRAFT_LLM_OPENROUTER_API_KEY"):
        checks.append(("OpenRouter", env["CODECRAFT_LLM_OPENROUTER_API_KEY"]))
    if env.get("CODECRAFT_LLM_GROQ_API_KEY"):
        checks.append(("Groq", env["CODECRAFT_LLM_GROQ_API_KEY"]))
    if env.get("CODECRAFT_LLM_GEMINI_API_KEY"):
        checks.append(("Gemini", env["CODECRAFT_LLM_GEMINI_API_KEY"]))

    if not checks:
        console.print("[yellow]No API keys configured. Run [bold]codecraft setup[/] first.[/]")
        return

    validators = {
        "OpenAI": _validate_openai,
        "OpenRouter": _validate_openrouter,
        "Groq": _validate_groq,
        "Gemini": _validate_gemini,
    }

    async def run_checks():
        results = []
        for name, key in checks:
            fn = validators.get(name)
            if fn:
                ok, msg = await fn(key)
                results.append((name, ok, msg))
        return results

    results = asyncio.run(run_checks())

    table = Table(title="API Key Validation Results")
    table.add_column("Provider", style="cyan")
    table.add_column("Result", style="green")
    table.add_column("Details")

    for name, ok, msg in results:
        table.add_row(
            name,
            "[green]PASS[/]" if ok else "[red]FAIL[/]",
            msg,
        )

    console.print(table)


project_app = typer.Typer(help="Project management commands")
app.add_typer(project_app, name="project")

memory_app = typer.Typer(help="Memory management commands")
app.add_typer(memory_app, name="memory")


@project_app.command("list")
def project_list() -> None:
    """List all CodeCraft projects."""
    projects = project_store.list_projects()
    if not projects:
        console.print("[dim]No projects found. Create one with: codecraft init[/]")
        return

    table = Table(title="Projects")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Updated", style="dim")
    table.add_column("Path")

    for p in projects:
        table.add_row(
            p.get("name", "?"),
            p.get("status", "?"),
            p.get("updated_at", "")[:19] if p.get("updated_at") else "?",
            p.get("_path", ""),
        )
    console.print(table)


@project_app.command("load")
def project_load(
    path: str = typer.Argument(..., help="Path to the project directory"),
) -> None:
    """Load an existing project and show its status."""
    try:
        manifest = project_store.load(path)
        console.print(Panel.fit(
            f"[bold]Name:[/] {manifest.get('name', '?')}\n"
            f"[bold]Status:[/] {manifest.get('status', '?')}\n"
            f"[bold]Phases:[/] {manifest.get('phases_completed', [])}\n"
            f"[bold]Artifacts:[/] {list(manifest.get('artifacts', {}).keys())}\n"
            f"[bold]Path:[/] [dim]{manifest.get('_path', path)}[/]",
            title=f"[bold cyan]Project: {manifest.get('name', 'Unknown')}[/]",
            border_style="cyan",
        ))
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")


@project_app.command("export")
def project_export(
    path: str = typer.Argument(..., help="Path to the project directory"),
    output: str = typer.Option(None, "--output", "-o", help="Output archive path"),
) -> None:
    """Export a project to a .codecraft.tar.gz archive."""
    try:
        result = project_store.export_project(path, output)
        console.print(f"[green]Exported:[/] {result}")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")


@project_app.command("import")
def project_import(
    archive: str = typer.Argument(..., help="Path to the .codecraft.tar.gz archive"),
    output: str = typer.Option(None, "--output", "-o", help="Output directory"),
) -> None:
    """Import a project from a .codecraft.tar.gz archive."""
    try:
        manifest = project_store.import_project(archive, output)
        console.print(f"[green]Imported:[/] {manifest.get('name', '?')} -> {manifest.get('_path', '?')}")
    except (FileNotFoundError, FileExistsError) as e:
        console.print(f"[red]{e}[/]")


@project_app.command("delete")
def project_delete(
    path: str = typer.Argument(..., help="Path to project directory to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a project and all its files."""
    if not force and not Confirm.ask(f"[red]Delete {path}?[/] This cannot be undone."):
        return
    project_store.delete(path)
    console.print(f"[green]Deleted:[/] {path}")


@memory_app.command("show")
def memory_show() -> None:
    """Show memory store statistics."""
    memory = get_memory()
    stats = memory.get_stats()
    table = Table(title="Agent Memory Store")
    table.add_column("Collection", style="cyan")
    table.add_column("Memories")
    for name, count in sorted(stats.items()):
        table.add_row(name, str(count))
    console.print(table)


@memory_app.command("clear")
def memory_clear(
    agent: str = typer.Option(None, "--agent", "-a", help="Clear specific agent memory"),
    project: str = typer.Option(None, "--project", "-p", help="Clear project memories"),
) -> None:
    """Clear agent or project memory."""
    memory = get_memory()
    if agent:
        memory.clear_agent_memory(agent)
        console.print(f"[green]Cleared memory for agent: {agent}[/]")
    elif project:
        deleted = memory.clear_project_memory(project)
        console.print(f"[green]Cleared {deleted} memories for project: {project}[/]")
    else:
        console.print("[yellow]Use --agent <name> or --project <name>[/]")


@app.command()
def thinktank(
    task: str = typer.Argument(..., help="Task for agents to collaborate on"),
    agents: str = typer.Option("researcher,planner,architect", "--agents", "-a", help="Comma-separated agent names"),
    rounds: int = typer.Option(3, "--rounds", "-r", help="Number of think-tank rounds"),
    workdir: str = typer.Option(None, "--workdir", "-w", help="Working directory"),
) -> None:
    """Run a think-tank session with multiple agents collaborating on a task."""
    from codecraft.agents import get_agent
    from codecraft.llm.models import resolve_model_for_agent
    from codecraft.agents.base import AgentContext

    agent_names = [a.strip() for a in agents.split(",")]
    workdir_path = workdir or str(Path.cwd() / "thinktank")
    Path(workdir_path).mkdir(parents=True, exist_ok=True)

    ctx = AgentContext(
        run_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        project_name="thinktank",
        project_description=task,
        workdir=workdir_path,
    )

    agent_instances = []
    console.print(f"[bold cyan]Think Tank[/]: {len(agent_names)} agents, {rounds} rounds\n")
    for name in agent_names:
        try:
            model, provider = resolve_model_for_agent(name)
            agent = get_agent(name)
            agent.set_context(ctx)
            agent.enable_memory()
            console.print(f"  [green]✓[/] {name} ({model} via {provider})")
            agent_instances.append(agent)
        except Exception as e:
            console.print(f"  [red]✗[/] {name}: {e}")

    if len(agent_instances) < 2:
        console.print("[red]Need at least 2 agents for think-tank[/]")
        return

    tank = ThinkTank(max_rounds=rounds)

    def handle(e, d):
        if e == "agent_start":
            console.print(f"  [cyan]▶[/] {d.get('agent', '?')} thinking...")
        elif e == "agent_complete":
            console.print(f"  [green]✓[/] {d.get('agent', '?')} done")
        elif e == "thinktank_converged":
            console.print(f"  [bold green]🤝 Converged at round {d.get('round', '?')}[/]")

    tank.on_event(handle)

    with console.status("[cyan]Think Tank in session...[/]", spinner="dots"):
        result = asyncio.run(tank.collaborate(agent_instances, task, ctx))

    console.print(f"\n[bold]Final Solution:[/]")
    console.print(result["final_solution"][:3000])
    console.print(f"\n[dim]Rounds: {len(result['transcript'])} messages | Converged: {result['converged']}[/]")

    for agent in agent_instances:
        try:
            asyncio.run(agent.close())
        except Exception:
            pass


if __name__ == "__main__":
    app()
