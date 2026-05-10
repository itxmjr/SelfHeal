from __future__ import annotations

import logging
from typing import Optional

from anthropic import Anthropic
from .base import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20240620"):
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.7, 
             max_tokens: int = 2048) -> LLMResponse:
        # Anthropic uses 'system' as a top-level parameter
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        chat_messages = [m for m in messages if m["role"] != "system"]

        try:
            response = self.client.messages.create(
                model=self.model,
                system=system_msg,
                messages=chat_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return LLMResponse(
                content=response.content[0].text,
                model=self.model,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
            )
        except Exception as e:
            logger.error(f"Anthropic chat failed: {e}")
            raise

    def vision(self, prompt: str, image_b64: str, model: str | None = None) -> LLMResponse:
        target_model = model or self.model
        try:
            response = self.client.messages.create(
                model=target_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=1024,
            )
            return LLMResponse(
                content=response.content[0].text,
                model=target_model,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
            )
        except Exception as e:
            logger.error(f"Anthropic vision failed: {e}")
            raise
