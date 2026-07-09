from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODECRAFT_LLM_", env_file=".env", extra="ignore")

    provider: str = "openai"
    model: str = "gpt-4o"

    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_admin_key: Optional[str] = None

    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    ollama_host: str = "http://localhost:11434"

    groq_api_key: Optional[str] = None
    groq_base_url: str = "https://api.groq.com/openai/v1"

    gemini_api_key: Optional[str] = None

    fallback_chain: list[str] = ["openai", "openrouter", "groq", "ollama"]
    max_retries: int = 3
    request_timeout: int = 120
    temperature: float = 0.7
    max_tokens: int = 16384


class DeployConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODECRAFT_DEPLOY_", env_file=".env", extra="ignore")

    vps_host: Optional[str] = None
    vps_user: str = "root"
    vps_ssh_key: Optional[str] = None
    vps_port: int = 22

    domain: str = "gincso.tech"

    github_token: Optional[str] = None
    github_user: Optional[str] = None

    cloudflare_tunnel_token: Optional[str] = None
    cloudflare_zone_id: Optional[str] = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODECRAFT_", env_file=".env", extra="ignore")

    data_dir: str = str(Path.home() / ".codecraft")
    projects_dir: str = str(Path.cwd() / "projects")
    log_level: str = "INFO"
    max_concurrent_agents: int = 3
    sandbox_enabled: bool = True
    require_tool_approval: bool = True

    llm: LLMConfig = LLMConfig()
    deploy: DeployConfig = DeployConfig()


settings = Settings()
