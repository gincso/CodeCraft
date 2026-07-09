from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Cost tiers: free, micro, cheap, standard, premium
# Prices are per 1M tokens (input/output)


@dataclass
class ModelSpec:
    name: str
    provider: str
    cost_tier: str  # free, micro, cheap, standard, premium
    description: str
    context_window: int = 128000
    supports_tools: bool = True
    openrouter_id: Optional[str] = None


# All available models ranked by cost-effectiveness
ALL_MODELS: list[ModelSpec] = [
    # ===== FREE TIER =====
    ModelSpec("gemini-2.0-flash", "gemini", "free",
              "Google Gemini Flash 2.0 - fast, capable, free tier"),
    ModelSpec("llama-3.1-8b-instruct", "openrouter", "free",
              "Meta Llama 3.1 8B - fast, decent reasoning, free on OpenRouter",
              openrouter_id="meta-llama/llama-3.1-8b-instruct"),
    ModelSpec("gemma-2-9b-it", "groq", "free",
              "Google Gemma 2 9B - fast small model, free on Groq"),

    # ===== MICRO COST (<$0.10/M tokens) =====
    ModelSpec("gpt-4o-mini", "openai", "micro",
              "OpenAI GPT-4o-mini - excellent quality/price ratio"),
    ModelSpec("gemini-1.5-flash", "gemini", "micro",
              "Google Gemini 1.5 Flash - good reasoning, very cheap"),
    ModelSpec("llama-3.1-70b-versatile", "groq", "micro",
              "Groq fast-serving Llama 3.1 70B"),
    ModelSpec("llama-3.3-70b-versatile", "groq", "micro",
              "Groq fast-serving Llama 3.3 70B - latest"),
    ModelSpec("mixtral-8x7b-32768", "groq", "micro",
              "Mistral Mixtral 8x7B - strong MoE model"),
    ModelSpec("llama-3.1-70b", "openrouter", "micro",
              "Llama 3.1 70B on OpenRouter - cheap",
              openrouter_id="meta-llama/llama-3.1-70b-instruct"),
    ModelSpec("qwen-2.5-72b", "openrouter", "micro",
              "Qwen 2.5 72B - strong open model",
              openrouter_id="qwen/qwen-2.5-72b-instruct"),

    # ===== CHEAP (<$1/M tokens) =====
    ModelSpec("claude-3.5-haiku", "openrouter", "cheap",
              "Anthropic Claude 3.5 Haiku - fast, capable",
              openrouter_id="anthropic/claude-3.5-haiku"),
    ModelSpec("mistral-large", "openrouter", "cheap",
              "Mistral Large - strong all-rounder",
              openrouter_id="mistralai/mistral-large"),

    # ===== STANDARD =====
    ModelSpec("gpt-4o", "openai", "standard",
              "OpenAI GPT-4o - top-tier reasoning and code"),
    ModelSpec("gemini-2.0-pro", "gemini", "standard",
              "Google Gemini 2.0 Pro - best Gemini"),
    ModelSpec("claude-sonnet-4", "openrouter", "standard",
              "Anthropic Claude Sonnet 4 - excellent code",
              openrouter_id="anthropic/claude-sonnet-4-20250514"),
]


def get_model(name: str) -> Optional[ModelSpec]:
    for m in ALL_MODELS:
        if m.name == name:
            return m
    return None


def get_models_by_tier(tier: str) -> list[ModelSpec]:
    return [m for m in ALL_MODELS if m.cost_tier == tier]


# Agent → optimal model mapping (cost-optimized)
AGENT_MODEL_MAP: dict[str, list[str]] = {
    "researcher": [
        "llama-3.1-8b-instruct",  # OpenRouter free tier - always available
        "qwen-2.5-72b",
        "gpt-4o-mini",
    ],
    "planner": [
        "llama-3.1-8b-instruct",
        "qwen-2.5-72b",
        "gpt-4o-mini",
    ],
    "architect": [
        "llama-3.1-8b-instruct",
        "qwen-2.5-72b",
        "gpt-4o-mini",
    ],
    "developer": [
        "llama-3.1-8b-instruct",
        "mistral-large",
        "gpt-4o-mini",
    ],
    "reviewer": [
        "llama-3.1-8b-instruct",
        "qwen-2.5-72b",
    ],
    "tester": [
        "llama-3.1-8b-instruct",
        "qwen-2.5-72b",
    ],
    "devops": [
        "llama-3.1-8b-instruct",
        "qwen-2.5-72b",
    ],
    "security": [
        "llama-3.1-8b-instruct",
        "qwen-2.5-72b",
    ],
}


def get_agent_models(agent_name: str) -> list[str]:
    return AGENT_MODEL_MAP.get(agent_name, ["gpt-4o-mini", "gemini-2.0-flash", "llama-3.3-70b-versatile"])


def resolve_model_for_agent(agent_name: str) -> tuple[str, str]:
    """Return (model_name, provider_name) for an agent, selecting cheapest available."""
    models = get_agent_models(agent_name)
    from codecraft.config import settings

    available_providers = {
        "gpt-4o-mini": ("openai", "gpt-4o-mini"),
        "gpt-4o": ("openai", "gpt-4o"),
        "gemini-2.0-flash": ("gemini", "gemini-2.0-flash"),
        "gemini-1.5-flash": ("gemini", "gemini-1.5-flash"),
        "gemini-2.0-pro": ("gemini", "gemini-2.0-pro"),
        "llama-3.1-70b-versatile": ("groq", "llama-3.1-70b-versatile"),
        "llama-3.3-70b-versatile": ("groq", "llama-3.3-70b-versatile"),
        "mixtral-8x7b-32768": ("groq", "mixtral-8x7b-32768"),
        "gemma-2-9b-it": ("groq", "gemma-2-9b-it"),
        "llama-3.1-70b": ("openrouter", "meta-llama/llama-3.1-70b-instruct"),
        "llama-3.1-8b-instruct": ("openrouter", "meta-llama/llama-3.1-8b-instruct"),
        "claude-3.5-haiku": ("openrouter", "anthropic/claude-3.5-haiku"),
        "qwen-2.5-72b": ("openrouter", "qwen/qwen-2.5-72b-instruct"),
        "claude-sonnet-4": ("openrouter", "anthropic/claude-sonnet-4-20250514"),
        "mistral-large": ("openrouter", "mistralai/mistral-large"),
    }

    for model_name in models:
        provider_info = available_providers.get(model_name)
        if not provider_info:
            continue
        provider, actual_model = provider_info

        has_key = {
            "openai": settings.llm.openai_api_key,
            "gemini": settings.llm.gemini_api_key,
            "groq": settings.llm.groq_api_key,
            "openrouter": settings.llm.openrouter_api_key,
        }.get(provider)

        if has_key or provider == "ollama":
            return actual_model, provider

    fallback = available_providers.get(models[0], ("openai", models[0]))
    return fallback[1], fallback[0]
