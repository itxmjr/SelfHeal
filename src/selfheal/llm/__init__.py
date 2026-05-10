from __future__ import annotations

import logging

from .base import LLMClient, LLMResponse as LLMResponse
from .nim import NIMClient
from .ollama import OllamaClient
from ..config import load_config

logger = logging.getLogger(__name__)


class FallbackLLMClient(LLMClient):
    def __init__(self, primary: LLMClient, fallback: LLMClient):
        self.primary = primary
        self.fallback = fallback

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.7,
             max_tokens: int = 2048) -> LLMResponse:
        try:
            return self.primary.chat(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception:
            logger.exception("Primary LLM chat failed, falling back to Ollama")
            return self.fallback.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def vision(self, prompt: str, image_b64: str, model: str | None = None) -> LLMResponse:
        try:
            return self.primary.vision(prompt, image_b64, model=model)
        except Exception:
            logger.exception("Primary LLM vision failed, falling back to Ollama")
            return self.fallback.vision(prompt, image_b64, model=model)


def get_llm_client() -> LLMClient:
    config = load_config()
    llm_config = config["llm"]
    provider = llm_config["provider"]

    if provider == "nim":
        nim_cfg = llm_config["nim"]
        api_key = nim_cfg.get("api_key", "")
        if not api_key:
            import os
            api_key = os.environ.get("NVIDIA_API_KEY", "")
        if not api_key:
            raise ValueError(
                "NVIDIA NIM API key not set. "
                "Run: selfheal config set llm.nim.api_key <api-key> "
                "or set NVIDIA_API_KEY env var."
            )
        return NIMClient(
            api_key=api_key,
            model=nim_cfg.get("model", "meta/llama-3.3-70b-instruct"),
            base_url=nim_cfg.get("base_url", "https://integrate.api.nvidia.com/v1"),
        )
    elif provider == "ollama":
        ollama_cfg = llm_config["ollama"]
        return OllamaClient(
            model=ollama_cfg.get("model", "llama3.2"),
            base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def get_llm_with_fallback() -> LLMClient:
    try:
        primary = get_llm_client()
    except Exception:
        logger.exception("Configured LLM provider failed, falling back to Ollama")
        try:
            return OllamaClient()
        except Exception:
            raise RuntimeError(
                "No LLM available. Configure NVIDIA NIM API key or start Ollama."
            )

    try:
        fallback = OllamaClient()
    except Exception:
        return primary
    return FallbackLLMClient(primary, fallback)
