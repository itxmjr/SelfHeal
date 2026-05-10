import copy
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env if present

CONFIG_DIR = Path(os.environ.get("SELFHEAL_CONFIG", Path.home() / ".config" / "selfheal"))
DATA_DIR = Path(os.environ.get("SELFHEAL_DATA", Path.home() / ".local" / "share" / "selfheal"))
DB_PATH = DATA_DIR / "selfheal.db"
LIFE_MODEL_PATH = CONFIG_DIR / "life_model.yaml"
CONFIG_PATH = CONFIG_DIR / "config.yaml"
WALLPAPER_DATA_PATH = DATA_DIR / "wallpaper_data.json"

DEFAULT_CONFIG = {
    "llm": {
        "provider": "nim",
        "nim": {
            "api_key": "",
            "model": "meta/llama-3.3-70b-instruct",
            "base_url": "https://integrate.api.nvidia.com/v1",
        },
        "ollama": {
            "model": "llama3.2",
            "base_url": "http://localhost:11434",
        },
        "openai": {
            "api_key": "",
            "model": "gpt-4o",
        },
        "anthropic": {
            "api_key": "",
            "model": "claude-3-5-sonnet-20240620",
        },
        "routing": {
            "scheduling": "anthropic",
            "interview": "anthropic",
            "analysis": "nim",
            "fallback": "ollama",
        },
    },
    "obsidian": {
        "vault_path": "",
    },
    "clickup": {
        "api_token": "",
        "list_ids": [],
    },
    "wallpaper": {
        "enabled": True,
        "update_interval_seconds": 60,
    },
    "scoring": {
        "weights": {
            "task_completion": 40,
            "time_utilization": 30,
            "goal_alignment": 20,
            "consistency_bonus": 10,
        },
        "streak_threshold": 70,
    },
}


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Override config dict with environment variables."""
    # LLM
    # We only apply env overrides if the variable actually exists and is not empty
    # to avoid overwriting YAML configs with empty/default env values
    if "SELFHEAL_LLM_PROVIDER" in os.environ:
        config["llm"]["provider"] = os.environ["SELFHEAL_LLM_PROVIDER"]
    # LLM
    if "NVIDIA_API_KEY" in os.environ:
        config["llm"]["nim"]["api_key"] = os.environ["NVIDIA_API_KEY"]
    if "OPENAI_API_KEY" in os.environ:
        config["llm"]["openai"]["api_key"] = os.environ["OPENAI_API_KEY"]
    if "ANTHROPIC_API_KEY" in os.environ:
        config["llm"]["anthropic"]["api_key"] = os.environ["ANTHROPIC_API_KEY"]
    if "SELFHEAL_NIM_MODEL" in os.environ:
        config["llm"]["nim"]["model"] = os.environ["SELFHEAL_NIM_MODEL"]
    if "SELFHEAL_NIM_BASE_URL" in os.environ:
        config["llm"]["nim"]["base_url"] = os.environ["SELFHEAL_NIM_BASE_URL"]
    if "SELFHEAL_OLLAMA_MODEL" in os.environ:
        config["llm"]["ollama"]["model"] = os.environ["SELFHEAL_OLLAMA_MODEL"]
    if "SELFHEAL_OLLAMA_BASE_URL" in os.environ:
        config["llm"]["ollama"]["base_url"] = os.environ["SELFHEAL_OLLAMA_BASE_URL"]

    # Obsidian
    if "SELFHEAL_OBSIDIAN_VAULT_PATH" in os.environ:
        config["obsidian"]["vault_path"] = os.environ["SELFHEAL_OBSIDIAN_VAULT_PATH"]

    # ClickUp
    if "SELFHEAL_CLICKUP_API_TOKEN" in os.environ:
        config["clickup"]["api_token"] = os.environ["SELFHEAL_CLICKUP_API_TOKEN"]
    if "SELFHEAL_CLICKUP_LIST_IDS" in os.environ:
        config["clickup"]["list_ids"] = [
            x.strip() for x in os.environ["SELFHEAL_CLICKUP_LIST_IDS"].split(",") if x.strip()
        ]
    elif "SELFHEAL_CLICKUP_LIST_ID" in os.environ:
        config["clickup"]["list_ids"] = [os.environ["SELFHEAL_CLICKUP_LIST_ID"]]

    # Wallpaper
    if "SELFHEAL_WALLPAPER_ENABLED" in os.environ:
        config["wallpaper"]["enabled"] = os.environ["SELFHEAL_WALLPAPER_ENABLED"].lower() in ("true", "1", "yes")
    if "SELFHEAL_WALLPAPER_INTERVAL" in os.environ:
        try:
            config["wallpaper"]["update_interval_seconds"] = int(os.environ["SELFHEAL_WALLPAPER_INTERVAL"])
        except ValueError:
            pass

    return config


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_dirs()

    # Check what paths we're actually resolving
    if os.environ.get("SELFHEAL_CONFIG"):
        config_path = Path(os.environ["SELFHEAL_CONFIG"]) / "config.yaml"
    else:
        config_path = CONFIG_PATH

    if config_path.exists():
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        # Ensure we deep merge into a FRESH copy of the default dict
        base = _deep_merge({}, DEFAULT_CONFIG)
        merged = _deep_merge(base, user_config)
        return _apply_env_overrides(merged)
    return _apply_env_overrides(_deep_merge({}, DEFAULT_CONFIG))


def save_config(config: dict[str, Any]):
    ensure_dirs()
    if os.environ.get("SELFHEAL_CONFIG"):
        config_path = Path(os.environ["SELFHEAL_CONFIG"]) / "config.yaml"
    else:
        config_path = CONFIG_PATH

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def set_config_path(path: str, raw_value: str) -> Any:
    default_value = get_config_path(DEFAULT_CONFIG, path)
    if isinstance(default_value, dict):
        raise ValueError(f"Cannot set non-leaf config path: {path}")
    value = _convert_config_value(raw_value, default_value)
    config = load_config()
    _set_config_path_value(config, path, value)
    save_config(config)
    return value


def get_config_path(config: dict[str, Any], path: str) -> Any:
    current: Any = config
    for part in _split_config_path(path):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(_invalid_config_path_message(path))
        current = current[part]
    return current


def valid_config_paths() -> list[str]:
    paths: list[str] = []

    def walk(prefix: str, value: Any) -> None:
        if not isinstance(value, dict):
            paths.append(prefix)
            return
        for key, child in value.items():
            walk(f"{prefix}.{key}" if prefix else key, child)

    walk("", DEFAULT_CONFIG)
    return paths


def _set_config_path_value(config: dict[str, Any], path: str, value: Any) -> None:
    current: dict[str, Any] = config
    parts = _split_config_path(path)
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            raise ValueError(_invalid_config_path_message(path))
        current = next_value
    current[parts[-1]] = value


def _split_config_path(path: str) -> list[str]:
    parts = path.split(".")
    if not path or any(part == "" for part in parts):
        raise ValueError(_invalid_config_path_message(path))
    return parts


def _invalid_config_path_message(path: str) -> str:
    return f"Invalid config path '{path}'. Valid paths: {', '.join(valid_config_paths())}"


def _convert_config_value(raw_value: str, default_value: Any) -> Any:
    if isinstance(default_value, bool):
        lowered = raw_value.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"Expected boolean value for this path, got: {raw_value}")

    if isinstance(default_value, int):
        try:
            return int(raw_value)
        except ValueError as error:
            raise ValueError(f"Expected integer value for this path, got: {raw_value}") from error

    if isinstance(default_value, float):
        try:
            return float(raw_value)
        except ValueError as error:
            raise ValueError(f"Expected numeric value for this path, got: {raw_value}") from error

    return raw_value


def init_config():
    ensure_dirs()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)


def load_life_model() -> dict[str, Any] | None:
    if LIFE_MODEL_PATH.exists():
        with open(LIFE_MODEL_PATH) as f:
            return yaml.safe_load(f)
    return None


def save_life_model(model: dict[str, Any]):
    ensure_dirs()
    with open(LIFE_MODEL_PATH, "w") as f:
        yaml.dump(model, f, default_flow_style=False, sort_keys=False)



def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
