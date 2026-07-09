from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from codecraft.agents.base import AgentContext
from codecraft.agents import (
    ResearcherAgent, PlannerAgent, ArchitectAgent, DeveloperAgent,
    ReviewerAgent, TesterAgent, DevOpsAgent, SecurityAgent,
)
from codecraft.tools.filesystem import ReadFileTool, WriteFileTool, ListDirectoryTool, SearchFilesTool, GrepTool
from codecraft.tools.shell import ShellTool
from codecraft.tools.web_search import WebSearchTool, WebFetchTool
from codecraft.tools.code_runner import CodeRunnerTool
from codecraft.tools.git import GitTool
from codecraft.tools.github_search import GitHubSearchTool, GitHubRepoInspectTool
from codecraft.tools.package_search import PackageSearchTool
from codecraft.tools.discovery import ToolDiscovery
from codecraft.llm.models import resolve_model_for_agent, get_agent_models
from codecraft.state.store import project_store
from codecraft.config import settings

logger = logging.getLogger(__name__)


class Phase(str, Enum):
    INIT = "init"
    RESEARCH = "research"
    PLANNING = "planning"
    ARCHITECTURE = "architecture"
    DEVELOPMENT = "development"
    REVIEW = "review"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    SECURITY = "security"
    COMPLETE = "complete"
    FAILED = "failed"


PIPELINE_FLOW: list[tuple[Phase, type, str]] = [
    (Phase.RESEARCH, ResearcherAgent, "research_report.md"),
    (Phase.PLANNING, PlannerAgent, "project_plan.md"),
    (Phase.ARCHITECTURE, ArchitectAgent, "architecture.md"),
    (Phase.DEVELOPMENT, DeveloperAgent, None),
    (Phase.REVIEW, ReviewerAgent, "code_review.md"),
    (Phase.TESTING, TesterAgent, "test_report.md"),
    (Phase.DEPLOYMENT, DevOpsAgent, "deploy_config.md"),
    (Phase.SECURITY, SecurityAgent, "security_audit.md"),
]


class Orchestrator:
    def __init__(
        self,
        project_name: str,
        project_description: str,
        workdir: str,
        mode: str = "pipeline",
    ):
        self.project_id = str(uuid.uuid4())
        self.run_id = str(uuid.uuid4())
        self.project_name = project_name
        self.project_description = project_description
        self.workdir = Path(workdir)
        self.mode = mode
        self.phase: Phase = Phase.INIT
        self.artifacts: dict[str, str] = {}
        self.agent_outputs: dict[str, str] = {}
        self.total_tokens = 0
        self.total_cost = 0.0
        self.errors: list[str] = []
        self._handlers: list[Callable[[str, dict[str, Any]], None]] = []
        self._paused = False
        self._aborted = False

        self.workdir.mkdir(parents=True, exist_ok=True)

    def on_event(self, handler: Callable[[str, dict[str, Any]], None]) -> None:
        self._handlers.append(handler)

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        data["project"] = self.project_name
        data["phase"] = self.phase.value
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        for handler in self._handlers:
            try:
                handler(event, data)
            except Exception:
                pass

    def _get_tools_for_agent(self, agent_name: str, workdir: str) -> list:
        common = [ReadFileTool(workdir=workdir), WriteFileTool(workdir=workdir),
                   ListDirectoryTool(workdir=workdir), GrepTool(workdir=workdir),
                   SearchFilesTool(workdir=workdir)]

        agent_tools = {
            "researcher": [WebSearchTool(workdir=workdir), WebFetchTool(workdir=workdir),
                          GitHubSearchTool(workdir=workdir), GitHubRepoInspectTool(workdir=workdir),
                          PackageSearchTool(workdir=workdir), ToolDiscovery(workdir=workdir)],
            "planner": [WebSearchTool(workdir=workdir), GitHubSearchTool(workdir=workdir),
                       PackageSearchTool(workdir=workdir)],
            "architect": [WebSearchTool(workdir=workdir), GitHubSearchTool(workdir=workdir),
                         GitHubRepoInspectTool(workdir=workdir), PackageSearchTool(workdir=workdir),
                         ToolDiscovery(workdir=workdir)],
            "developer": [ShellTool(workdir=workdir), CodeRunnerTool(workdir=workdir),
                         GitTool(workdir=workdir), PackageSearchTool(workdir=workdir),
                         GitHubSearchTool(workdir=workdir), ToolDiscovery(workdir=workdir)],
            "reviewer": [ShellTool(workdir=workdir), GrepTool(workdir=workdir),
                        GitHubSearchTool(workdir=workdir)],
            "tester": [ShellTool(workdir=workdir), CodeRunnerTool(workdir=workdir),
                      PackageSearchTool(workdir=workdir)],
            "devops": [ShellTool(workdir=workdir), GitTool(workdir=workdir),
                      PackageSearchTool(workdir=workdir), ToolDiscovery(workdir=workdir)],
            "security": [ShellTool(workdir=workdir), GrepTool(workdir=workdir),
                        WebSearchTool(workdir=workdir), GitHubSearchTool(workdir=workdir)],
        }
        return common + agent_tools.get(agent_name, [])

    def _make_context(self) -> AgentContext:
        return AgentContext(
            run_id=self.run_id,
            project_id=self.project_id,
            project_name=self.project_name,
            project_description=self.project_description,
            workdir=str(self.workdir),
        )

    async def run_pipeline(self) -> dict[str, Any]:
        self.phase = Phase.RESEARCH
        self._emit("pipeline_start", {"mode": "pipeline", "phases": len(PIPELINE_FLOW)})

        for phase, agent_cls, artifact_name in PIPELINE_FLOW:
            if self._aborted:
                break

            self.phase = phase
            agent_name = agent_cls.name if hasattr(agent_cls, "name") else phase.value

            model, provider = resolve_model_for_agent(agent_name)
            self._emit("agent_start", {
                "agent": agent_name,
                "phase": phase.value,
                "model": model,
                "provider": provider,
            })

            try:
                agent = agent_cls()
                agent.name = agent_name
                agent.default_model = model

                ctx = self._make_context()
                agent.set_context(ctx)

                tools = self._get_tools_for_agent(agent_name, str(self.workdir))
                agent.register_tools(tools)

                agent.on_event(lambda e, d, a=agent_name: self._emit(f"agent_{e}", {**d, "agent": a}))
                agent.enable_memory()

                input_text = self._build_agent_input(phase, artifact_name)
                self._emit("agent_running", {"agent": agent_name, "input_length": len(input_text)})

                result = await agent.run(input_text)

                self.agent_outputs[phase.value] = result

                try:
                    agent.memory.remember_artifact(
                        agent=agent_name,
                        filename=artifact_name or f"{phase.value}_output.md",
                        content=result[:5000],
                        project=self.project_name,
                    )
                    agent.memory.remember_conversation(
                        agent=agent_name,
                        role="output",
                        content=result[:2000],
                        project=self.project_name,
                    )
                except Exception:
                    pass
                self.total_tokens += 0

                if artifact_name:
                    artifact_path = self.workdir / artifact_name
                    artifact_path.write_text(result)
                    self.artifacts[phase.value] = str(artifact_path)
                    self._emit("artifact_saved", {"path": str(artifact_path), "phase": phase.value})

                self._save_state()

                self._emit("agent_complete", {
                    "agent": agent_name,
                    "phase": phase.value,
                    "output_length": len(result),
                    "model": model,
                })

                await agent.close()

            except Exception as e:
                logger.exception(f"Agent {agent_name} failed in phase {phase}")
                self.errors.append(f"{phase.value}: {e}")
                self._emit("agent_error", {"agent": agent_name, "error": str(e)})

                fallback_model, fallback_provider = resolve_model_for_agent(f"{agent_name}_fallback")
                if fallback_provider != provider:
                    try:
                        self._emit("agent_retry", {"agent": agent_name, "fallback_model": fallback_model})
                        agent = agent_cls()
                        agent.default_model = fallback_model
                        ctx = self._make_context()
                        agent.set_context(ctx)
                        agent.register_tools(self._get_tools_for_agent(agent_name, str(self.workdir)))
                        result = await agent.run(self._build_agent_input(phase, artifact_name))
                        self.agent_outputs[phase.value] = result
                        if artifact_name:
                            (self.workdir / artifact_name).write_text(result)
                            self.artifacts[phase.value] = str(self.workdir / artifact_name)
                        await agent.close()
                        self._emit("agent_complete", {"agent": agent_name, "fallback": True})
                        continue
                    except Exception as e2:
                        self.errors.append(f"{phase.value} fallback: {e2}")

                if phase in (Phase.RESEARCH, Phase.PLANNING, Phase.ARCHITECTURE):
                    self.phase = Phase.FAILED
                    break

        if not self._aborted and self.phase != Phase.FAILED:
            self.phase = Phase.COMPLETE

        self._emit("pipeline_complete", {
            "status": self.phase.value,
            "errors": len(self.errors),
            "artifacts": list(self.artifacts.keys()),
        })

        return {
            "status": self.phase.value,
            "artifacts": self.artifacts,
            "outputs": self.agent_outputs,
            "errors": self.errors,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
        }

    def _build_agent_input(self, phase: Phase, artifact_name: Optional[str]) -> str:
        previous_outputs = ""
        for prev_phase, _, _ in PIPELINE_FLOW:
            if prev_phase == phase:
                break
            if prev_phase.value in self.agent_outputs:
                prev_out = self.agent_outputs[prev_phase.value]
                prev_out_short = prev_out[:3000] if len(prev_out) > 3000 else prev_out
                previous_outputs += f"\n\n--- {prev_phase.value.upper()} OUTPUT ---\n{prev_out_short}\n"

        phase_prompts = {
            Phase.RESEARCH: f"Project: {self.project_name}\nDescription: {self.project_description}\n\nProduce a comprehensive research report.",
            Phase.PLANNING: f"Project: {self.project_name}\n\nBased on the research, create a detailed implementation plan.",
            Phase.ARCHITECTURE: f"Project: {self.project_name}\n\nBased on the plan and research, design the system architecture.",
            Phase.DEVELOPMENT: f"Project: {self.project_name}\n\nImplement the project based on the architecture, plan, and research. Create all necessary source files.",
            Phase.REVIEW: f"Project: {self.project_name}\n\nReview all code in the project directory. Check for bugs, security issues, and adherence to the architecture.",
            Phase.TESTING: f"Project: {self.project_name}\n\nWrite and run tests for the project code. Report coverage and any failures.",
            Phase.DEPLOYMENT: f"Project: {self.project_name}\n\nCreate deployment configuration. Set up Docker, CI/CD, and deployment scripts.",
            Phase.SECURITY: f"Project: {self.project_name}\n\nPerform a security audit of the project. Check for vulnerabilities, exposed secrets, and OWASP issues.",
        }

        prompt = phase_prompts.get(phase, f"Work on: {self.project_description}")
        if previous_outputs:
            prompt += f"\n\n## Previous Agent Outputs\n{previous_outputs}"
        return prompt

    def _save_state(self) -> None:
        try:
            manifest = {
                "name": self.project_name,
                "slug": self.project_name.lower().replace(" ", "-"),
                "description": self.project_description,
                "version": "0.1.0",
                "status": self.phase.value,
                "mode": self.mode,
                "phases_completed": [p for p, s in self.agent_outputs.items() if s],
                "artifacts": self.artifacts,
                "agent_outputs": {k: v[:200] for k, v in self.agent_outputs.items()},
                "total_tokens": self.total_tokens,
                "total_cost": self.total_cost,
                "errors": self.errors[-5:],
            }
            project_store.save(str(self.workdir), manifest)
        except Exception as e:
            logger.warning(f"Failed to save project state: {e}")

    def to_manifest(self) -> dict[str, Any]:
        return {
            "name": self.project_name,
            "slug": self.project_name.lower().replace(" ", "-"),
            "description": self.project_description,
            "version": "0.1.0",
            "status": self.phase.value,
            "mode": self.mode,
            "phases_completed": [p for p, s in self.agent_outputs.items() if s],
            "artifacts": self.artifacts,
            "agent_outputs": {k: v[:200] for k, v in self.agent_outputs.items()},
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "errors": self.errors[-5:],
        }

    async def run_dynamic(self) -> dict[str, Any]:
        self.phase = Phase.RESEARCH
        self._emit("pipeline_start", {"mode": "dynamic"})

        coordinator_prompt = f"""You are the CodeCraft Orchestrator. Your job is to coordinate a team of AI agents to build this project:

**Project**: {self.project_name}
**Description**: {self.project_description}

## Available Agents
- **researcher**: Domain research and requirements analysis
- **planner**: Project planning and task decomposition
- **architect**: System architecture and technical design
- **developer**: Code generation and implementation
- **reviewer**: Code review and quality assurance
- **tester**: Test generation and execution
- **devops**: Deployment and infrastructure
- **security**: Security audit and hardening

## Your Task
1. Decompose this project into phases
2. For each phase, decide which agents to run and in what order
3. After each agent completes, review their output and decide next steps
4. Continue until the project is complete

Start by initiating the research phase. What should the researcher investigate?"""

        try:
            from codecraft.llm import create_fallback_provider
            from codecraft.llm.base import LLMMessage

            provider = create_fallback_provider(names=["openai", "gemini", "groq", "openrouter"])
            messages = [LLMMessage(role="system", content=coordinator_prompt)]
            messages.append(LLMMessage(role="user", content=f"Start working on: {self.project_description}"))

            response = await provider.complete(messages)
            coordinator_output = response.content if hasattr(response, "content") else ""

            self._emit("coordinator_plan", {"plan": coordinator_output[:2000]})

            phases_to_run = self._parse_dynamic_phases(coordinator_output)

            for agent_name, task in phases_to_run:
                if self._aborted:
                    break

                model, provider = resolve_model_for_agent(agent_name)
                agent_cls = self._get_agent_class(agent_name)
                if not agent_cls:
                    continue

                self._emit("agent_start", {"agent": agent_name, "task": task[:200]})
                agent = agent_cls()
                agent.default_model = model
                ctx = self._make_context()
                agent.set_context(ctx)
                agent.register_tools(self._get_tools_for_agent(agent_name, str(self.workdir)))

                try:
                    result = await agent.run(task)
                    self.agent_outputs[agent_name] = result
                    self._emit("agent_complete", {"agent": agent_name, "output_length": len(result)})
                except Exception as e:
                    self.errors.append(f"{agent_name}: {e}")
                    self._emit("agent_error", {"agent": agent_name, "error": str(e)})
                finally:
                    await agent.close()

                artifact_path = self.workdir / f"{agent_name}_output.md"
                artifact_path.write_text(result)
                self.artifacts[agent_name] = str(artifact_path)

        except Exception as e:
            self.errors.append(f"dynamic: {e}")
            self.phase = Phase.FAILED

        self.phase = Phase.COMPLETE if not self.errors else Phase.FAILED
        self._emit("pipeline_complete", {"status": self.phase.value, "errors": len(self.errors)})

        return {
            "status": self.phase.value,
            "artifacts": self.artifacts,
            "outputs": self.agent_outputs,
            "errors": self.errors,
        }

    def _parse_dynamic_phases(self, coordinator_output: str) -> list[tuple[str, str]]:
        agents = ["researcher", "planner", "architect", "developer", "reviewer", "tester", "devops", "security"]
        phases: list[tuple[str, str]] = []

        lines = coordinator_output.split("\n")
        current_agent = None
        current_task: list[str] = []

        for line in lines:
            line_lower = line.lower()
            for agent in agents:
                if agent in line_lower and ("agent" in line_lower or "phase" in line_lower or "run" in line_lower or "start" in line_lower or "next" in line_lower):
                    if current_agent and current_task:
                        phases.append((current_agent, "\n".join(current_task)))
                    current_agent = agent
                    current_task = [line]
                    break
            else:
                if current_agent:
                    if line.strip():
                        current_task.append(line)
                    elif len(current_task) > 1:
                        pass

        if current_agent and current_task:
            phases.append((current_agent, "\n".join(current_task)))

        if not phases:
            phases = [
                ("researcher", f"Research: {self.project_description}"),
                ("planner", f"Plan: {self.project_description}"),
                ("architect", f"Architect: {self.project_description}"),
                ("developer", f"Develop: {self.project_description}"),
                ("reviewer", f"Review all code in {self.workdir}"),
                ("tester", f"Test all code in {self.workdir}"),
                ("devops", f"Create deploy config for {self.project_name}"),
                ("security", f"Security audit of {self.workdir}"),
            ]

        return phases

    def _get_agent_class(self, name: str):
        mapping = {
            "researcher": ResearcherAgent,
            "planner": PlannerAgent,
            "architect": ArchitectAgent,
            "developer": DeveloperAgent,
            "reviewer": ReviewerAgent,
            "tester": TesterAgent,
            "devops": DevOpsAgent,
            "security": SecurityAgent,
        }
        return mapping.get(name)

    def abort(self) -> None:
        self._aborted = True

    async def run(self) -> dict[str, Any]:
        if self.mode == "dynamic":
            return await self.run_dynamic()
        return await self.run_pipeline()
