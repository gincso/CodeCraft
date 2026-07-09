# CodeCraft

**Multi-agent AI-powered software development platform — from idea to deployed product.**

CodeCraft orchestrates a team of specialized AI agents (Researcher, Planner, Architect, Developer, Reviewer, Tester, DevOps, Security) to take your idea from concept to production deployment with zero manual intervention.

## Features

- **8 Specialized AI Agents** — Each agent has a specific role and tool access
- **Dual Orchestration Modes** — Simple pipeline or dynamic recursive agent spawning
- **Multi-LLM Support** — OpenAI, OpenRouter, Ollama, Groq with automatic fallback
- **Live Agent Theater** — Watch all agents work simultaneously in real-time
- **One-Click Deploy** — Auto-deploy to VPS via Cloudflare Tunnel → `project.gincso.tech`
- **Human-in-the-Loop** — Pause, inspect, approve, or edit at any phase
- **Project Memory** — Vector-based memory learns across projects
- **CLI + Web UI + API** — Terminal, browser dashboard, or programmatic access

## Quick Start

```bash
pip install -e .
codecraft init "Build a real-time chat app"
```

## Architecture

```
Idea → Researcher → Planner → Architect → Developer → Reviewer → Tester → DevOps → Deployed
```

## License

MIT
