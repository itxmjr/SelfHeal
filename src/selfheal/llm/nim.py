from __future__ import annotations
# pyright: reportMissingImports=false

import httpx
from selfheal import LLMError, retry_sync
from .base import LLMClient, LLMResponse


@retry_sync(max_attempts=3, base_delay=0.5, max_delay=5.0)
def _post_json(url: str, headers: dict[str, str], payload: dict, timeout: float) -> dict:
    try:
        resp = getattr(httpx, "post")(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise LLMError(f"NVIDIA NIM request failed: {exc}") from exc


class NIMClient(LLMClient):
    def __init__(self, api_key: str, model: str = "meta/llama-3.3-70b-instruct",
                 base_url: str = "https://integrate.api.nvidia.com/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.7,
             max_tokens: int = 2048) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = _post_json(
            f"{self.base_url}/chat/completions",
            headers,
            payload,
            60.0,
        )
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    def vision(self, prompt: str, image_b64: str, model: str | None = None) -> LLMResponse:
        v_model = model or "nvidia/llama-3.2-11b-vision-instruct"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": v_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                    ]
                }
            ],
            "max_tokens": 1024,
        }
        data = _post_json(
            f"{self.base_url}/chat/completions",
            headers,
            payload,
            60.0,
        )
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(content=content, model=v_model)
