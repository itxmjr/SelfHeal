from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient:
    def chat(self, messages: list[dict[str, str]], temperature: float = 0.7,
             max_tokens: int = 2048) -> LLMResponse:
        raise NotImplementedError

    def vision(self, prompt: str, image_b64: str, model: str | None = None) -> LLMResponse:
        """Analyze an image and return text description/extraction."""
        raise NotImplementedError("Vision not supported by this provider")
