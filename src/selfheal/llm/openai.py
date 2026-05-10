from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI
from .base import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.7, 
             max_tokens: int = 2048) -> LLMResponse:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=self.model,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )
        except Exception as e:
            logger.error(f"OpenAI chat failed: {e}")
            raise

    def vision(self, prompt: str, image_b64: str, model: str | None = None) -> LLMResponse:
        target_model = model or "gpt-4o"
        try:
            response = self.client.chat.completions.create(
                model=target_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                            },
                        ],
                    }
                ],
                max_tokens=1024,
            )
            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=target_model,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )
        except Exception as e:
            logger.error(f"OpenAI vision failed: {e}")
            raise
