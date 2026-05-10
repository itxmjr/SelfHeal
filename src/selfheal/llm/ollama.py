from __future__ import annotations
# pyright: reportMissingImports=false

import httpx
from selfheal import LLMError, retry_sync
from .base import LLMClient, LLMResponse


@retry_sync(max_attempts=3, base_delay=0.5, max_delay=5.0)
def _post_json(url: str, payload: dict, timeout: float) -> dict:
    try:
        resp = getattr(httpx, "post")(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc


class OllamaClient(LLMClient):
    def __init__(self, model: str = "llama3.2",
                 base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.7,
             max_tokens: int = 2048) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        data = _post_json(
            f"{self.base_url}/api/chat",
            payload,
            120.0,
        )
        content = data["message"]["content"]
        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    def vision(self, prompt: str, image_b64: str, model: str | None = None) -> LLMResponse:
        v_model = model or "llama3.2-vision"
        image_data_uri = f"data:image/png;base64,{image_b64}"
        payload = {
            "model": v_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_data_uri],
                }
            ],
            "stream": False,
            "options": {
                "num_predict": 1024,
            },
        }
        data = _post_json(
            f"{self.base_url}/api/chat",
            payload,
            120.0,
        )
        content = data["message"]["content"]
        return LLMResponse(
            content=content,
            model=v_model,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )
