from unittest.mock import patch

from selfheal.llm import FallbackLLMClient, OllamaClient, get_llm_client, get_llm_with_fallback
from selfheal.llm.base import LLMResponse


def test_ollama_vision_uses_native_image_payload_and_default_model():
    client = OllamaClient(base_url="http://ollama.test/")

    with patch(
        "selfheal.llm.ollama._post_json",
        return_value={
            "message": {"content": "extracted tasks"},
            "prompt_eval_count": 11,
            "eval_count": 7,
        },
    ) as post_json:
        response = client.vision("read this", "abc123")

    post_json.assert_called_once_with(
        "http://ollama.test/api/chat",
        {
            "model": "llama3.2-vision",
            "messages": [
                {
                    "role": "user",
                    "content": "read this",
                    "images": ["data:image/png;base64,abc123"],
                }
            ],
            "stream": False,
            "options": {
                "num_predict": 1024,
            },
        },
        120.0,
    )
    assert response == LLMResponse(
        content="extracted tasks",
        model="llama3.2-vision",
        prompt_tokens=11,
        completion_tokens=7,
    )


def test_ollama_vision_allows_custom_model_override():
    client = OllamaClient(model="llama3.2")

    with patch(
        "selfheal.llm.ollama._post_json",
        return_value={"message": {"content": "ok"}},
    ) as post_json:
        response = client.vision("describe", "base64-image", model="llava:13b")

    payload = post_json.call_args.args[1]
    assert payload["model"] == "llava:13b"
    assert payload["messages"][0]["images"] == ["data:image/png;base64,base64-image"]
    assert response == LLMResponse(content="ok", model="llava:13b")


def test_get_llm_client_returns_ollama_client_with_vision_support():
    config = {
        "llm": {
            "provider": "ollama",
            "ollama": {
                "model": "local-chat",
                "base_url": "http://localhost:11435",
            },
        }
    }

    with patch("selfheal.llm.load_config", return_value=config):
        client = get_llm_client()

    assert isinstance(client, OllamaClient)
    assert client.model == "local-chat"
    assert client.base_url == "http://localhost:11435"
    assert callable(client.vision)


def test_get_llm_client_nim_missing_key_mentions_config_set_command():
    config = {
        "llm": {
            "provider": "nim",
            "nim": {
                "api_key": "",
                "model": "meta/llama-3.3-70b-instruct",
                "base_url": "https://integrate.api.nvidia.com/v1",
            },
        }
    }

    with patch("selfheal.llm.load_config", return_value=config):
        with patch.dict("os.environ", {"NVIDIA_API_KEY": ""}, clear=True):
            try:
                get_llm_client()
            except ValueError as error:
                message = str(error)
            else:
                raise AssertionError("Expected missing NIM API key error")

    assert "selfheal config set llm.nim.api_key <api-key>" in message
    assert "NVIDIA_API_KEY" in message


def test_get_llm_with_fallback_returns_ollama_when_configured_provider_fails():
    config = {
        "llm": {
            "provider": "nim",
            "nim": {
                "api_key": "",
                "model": "meta/llama-3.3-70b-instruct",
                "base_url": "https://integrate.api.nvidia.com/v1",
            },
        }
    }

    with patch("selfheal.llm.load_config", return_value=config):
        with patch.dict("os.environ", {"NVIDIA_API_KEY": ""}, clear=True):
            client = get_llm_with_fallback()

    assert isinstance(client, OllamaClient)
    assert callable(client.vision)


def test_get_llm_with_fallback_uses_ollama_when_primary_chat_fails():
    primary = type("Primary", (), {"chat": lambda self, *args, **kwargs: (_ for _ in ()).throw(RuntimeError("nim down"))})()
    fallback_calls = []

    class Fallback:
        def chat(self, messages, temperature=0.7, max_tokens=2048):
            fallback_calls.append((messages, temperature, max_tokens))
            return LLMResponse("fallback", "ollama")

    client = FallbackLLMClient(primary, Fallback())

    assert client.chat([{"role": "user", "content": "hi"}], temperature=0.2, max_tokens=10).content == "fallback"
    assert fallback_calls == [([{"role": "user", "content": "hi"}], 0.2, 10)]


def test_get_llm_with_fallback_uses_ollama_when_primary_vision_fails():
    primary = type("Primary", (), {"vision": lambda self, *args, **kwargs: (_ for _ in ()).throw(RuntimeError("nim down"))})()
    fallback_calls = []

    class Fallback:
        def vision(self, prompt, image_b64, model=None):
            fallback_calls.append((prompt, image_b64, model))
            return LLMResponse("vision fallback", "ollama")

    client = FallbackLLMClient(primary, Fallback())

    assert client.vision("see", "abc", model="vision-model").content == "vision fallback"
    assert fallback_calls == [("see", "abc", "vision-model")]


def test_get_llm_with_fallback_wraps_constructed_primary_runtime_failures(monkeypatch):
    class Primary:
        def chat(self, messages, temperature=0.7, max_tokens=2048):
            raise RuntimeError("primary chat down")

        def vision(self, prompt, image_b64, model=None):
            raise RuntimeError("primary vision down")

    class Fallback:
        def chat(self, messages, temperature=0.7, max_tokens=2048):
            return LLMResponse("fallback chat", "ollama")

        def vision(self, prompt, image_b64, model=None):
            return LLMResponse("fallback vision", "ollama")

    monkeypatch.setattr("selfheal.llm.get_llm_client", lambda: Primary())
    monkeypatch.setattr("selfheal.llm.OllamaClient", lambda: Fallback())

    client = get_llm_with_fallback()

    assert client.chat([{"role": "user", "content": "hi"}]).content == "fallback chat"
    assert client.vision("see", "abc").content == "fallback vision"
