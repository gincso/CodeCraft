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
        "gemini-2.0-flash",      # free, good for web search and analysis
        "gpt-4o-mini",            # cheap fallback
        "llama-3.3-70b-versatile",
    ],
    "planner": [
        "llama-3.3-70b-versatile",  # free on Groq, strong reasoning
        "gpt-4o-mini",               # cheap fallback
        "gemini-2.0-flash",
    ],
    "architect": [
        "gemini-2.0-flash",        # free, good system design
        "llama-3.3-70b-versatile", # free on Groq
        "gpt-4o-mini",
    ],
    "developer": [
        "gpt-4o-mini",              # cheap, excellent code gen
        "llama-3.3-70b-versatile",  # free fallback
        "claude-3.5-haiku",
    ],
    "reviewer": [
        "llama-3.3-70b-versatile",  # free, good for review
        "gemini-2.0-flash",         # free fallback
        "gpt-4o-mini",
    ],
    "tester": [
        "llama-3.3-70b-versatile",  # free, good for test gen
        "gemini-2.0-flash",
        "gpt-4o-mini",
    ],
    "devops": [
        "llama-3.3-70b-versatile",  # free, good for config/code
        "gemini-2.0-flash",
        "gpt-4o-mini",
    ],
    "security": [
        "llama-3.3-70b-versatile",  # free, good for pattern matching
        "gemini-2.0-flash",
        "gpt-4o-mini",
    ],
}


def get_agent_models(agent_name: str) -> list[str]:
    return AGENT_MODEL_MAP.get(agent_name, ["gpt-4o-mini", "gemini-2.0-flash", "llama-3.3-70b-versatile"])


def resolve_model_for_agent(agent_name: str) -> tuple[str, str]:
    """Return (model_name, provider_name) for an agent, selecting cheapest available."""
    models = get_agent_models(agent_name)
    from codecraft.config import settings

    available_providers = {
        "gpt-4o-mini": "openai",
        "gpt-4o": "openai",
        "gemini-2.0-flash": "gemini",
        "gemini-1.5-flash": "gemini",
        "gemini-2.0-pro": "gemini",
        "llama-3.1-70b-versatile": "groq",
        "llama-3.3-70b-versatile": "groq",
        "mixtral-8x7b-32768": "groq",
        "gemma-2-9b-it": "groq",
        "llama-3.1-70b": "openrouter",
        "llama-3.1-8b-instruct": "openrouter",
        "claude-3.5-haiku": "openrouter",
        "qwen-2.5-72b": "openrouter",
        "claude-sonnet-4": "openrouter",
        "mistral-large": "openrouter",
    }

    for model_name in models:
        provider = available_providers.get(model_name, "openai")
        if provider == "openai" and settings.llm.openai_api_key:
            return model_name, provider
        if provider == "gemini" and settings.llm.gemini_api_key:
            return model_name, provider
        if provider == "groq" and settings.llm.groq_api_key:
            return model_name, provider
        if provider == "openrouter" and settings.llm.openrouter_api_key:
            return model_name, provider

    return models[0], available_providers.get(models[0], "openai")
