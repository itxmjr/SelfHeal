from __future__ import annotations

import logging
from typing import Optional, Dict

from .base import LLMClient, LLMResponse
from .nim import NIMClient
from .ollama import OllamaClient
from .openai import OpenAIClient
from .anthropic import AnthropicClient
from ..config import load_config

logger = logging.getLogger(__name__)

class LLMRouter(LLMClient):
    """Routes LLM calls to different providers based on task type or complexity."""
    
    def __init__(self):
        self.config = load_config()
        self.clients: Dict[str, LLMClient] = {}
        self._init_clients()

    def _init_clients(self):
        llm_cfg = self.config.get("llm", {})
        
        # Init Ollama (usually local, always available as fallback)
        ollama_cfg = llm_cfg.get("ollama", {})
        self.clients["ollama"] = OllamaClient(
            model=ollama_cfg.get("model", "llama3.2"),
            base_url=ollama_cfg.get("base_url", "http://localhost:11434")
        )

        # Init NIM
        nim_cfg = llm_cfg.get("nim", {})
        if nim_cfg.get("api_key"):
            self.clients["nim"] = NIMClient(
                api_key=nim_cfg["api_key"],
                model=nim_cfg.get("model", "meta/llama-3.3-70b-instruct"),
                base_url=nim_cfg.get("base_url", "https://integrate.api.nvidia.com/v1")
            )

        # Init OpenAI
        openai_cfg = llm_cfg.get("openai", {})
        if openai_cfg.get("api_key"):
            self.clients["openai"] = OpenAIClient(
                api_key=openai_cfg["api_key"],
                model=openai_cfg.get("model", "gpt-4o")
            )

        # Init Anthropic
        anthropic_cfg = llm_cfg.get("anthropic", {})
        if anthropic_cfg.get("api_key"):
            self.clients["anthropic"] = AnthropicClient(
                api_key=anthropic_cfg["api_key"],
                model=anthropic_cfg.get("model", "claude-3-5-sonnet-20240620")
            )

    def get_client(self, task_type: str = "fallback") -> LLMClient:
        routing = self.config.get("llm", {}).get("routing", {})
        provider_name = routing.get(task_type, routing.get("fallback", "ollama"))
        
        client = self.clients.get(provider_name)
        if not client:
            logger.warning(f"Provider {provider_name} not configured for task {task_type}, falling back to Ollama")
            return self.clients["ollama"]
        return client

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.7, 
             max_tokens: int = 2048) -> LLMResponse:
        # Default routing if not explicitly called via get_client
        return self.get_client().chat(messages, temperature, max_tokens)

    def vision(self, prompt: str, image_b64: str, model: str | None = None) -> LLMResponse:
        return self.get_client("analysis").vision(prompt, image_b64, model)


def get_llm_client(task_type: str = "fallback") -> LLMClient:
    """Convenience function to get a routed LLM client."""
    router = LLMRouter()
    return router.get_client(task_type)

def get_llm_with_fallback(task_type: str = "fallback") -> LLMClient:
    """Alias for get_llm_client for backward compatibility, now using routing."""
    return get_llm_client(task_type)
