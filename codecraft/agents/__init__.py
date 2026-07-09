"""Agent system for CodeCraft."""

from codecraft.agents.base import BaseAgent, AgentContext
from codecraft.agents.researcher import ResearcherAgent
from codecraft.agents.planner import PlannerAgent
from codecraft.agents.architect import ArchitectAgent
from codecraft.agents.developer import DeveloperAgent
from codecraft.agents.reviewer import ReviewerAgent
from codecraft.agents.tester import TesterAgent
from codecraft.agents.devops import DevOpsAgent
from codecraft.agents.security import SecurityAgent
from codecraft.agents.manager import ManagerAgent

AGENT_REGISTRY = {
    "researcher": ResearcherAgent,
    "planner": PlannerAgent,
    "architect": ArchitectAgent,
    "developer": DeveloperAgent,
    "reviewer": ReviewerAgent,
    "tester": TesterAgent,
    "devops": DevOpsAgent,
    "security": SecurityAgent,
    "manager": ManagerAgent,
}


def get_agent(name: str, **kwargs) -> BaseAgent:
    cls = AGENT_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown agent: {name}. Available: {list(AGENT_REGISTRY)}")
    return cls(**kwargs)


__all__ = [
    "BaseAgent", "AgentContext",
    "ResearcherAgent", "PlannerAgent", "ArchitectAgent", "DeveloperAgent",
    "ReviewerAgent", "TesterAgent", "DevOpsAgent", "SecurityAgent",
    "ManagerAgent", "AGENT_REGISTRY", "get_agent",
]
