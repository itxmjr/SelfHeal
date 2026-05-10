import os
import yaml
from unittest.mock import patch

from selfheal.config import load_config, DEFAULT_CONFIG

def test_load_default_config(mock_env):
    """Test that default config is loaded when no files exist."""
    config = load_config()
    assert config["llm"]["provider"] == "nim"
    assert config["wallpaper"]["enabled"] is True

def test_load_yaml_config(mock_env, temp_config_dir):
    """Test that YAML config overrides defaults."""
    config_dir = temp_config_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    yaml_path = config_dir / "config.yaml"
    custom_config = {
        "llm": {
            "provider": "ollama",
            "ollama": {
                "model": "custom-model"
            }
        }
    }
    
    with open(yaml_path, "w") as f:
        yaml.dump(custom_config, f)
        
    config = load_config()
    assert config["llm"]["provider"] == "ollama"
    assert config["llm"]["ollama"]["model"] == "custom-model"
    # Defaults should still exist
    assert config["wallpaper"]["enabled"] is True

def test_env_overrides(mock_env):
    """Test that environment variables override both default and YAML configs."""
    with patch.dict(os.environ, {"SELFHEAL_LLM_PROVIDER": "env_provider", "SELFHEAL_WALLPAPER_ENABLED": "false"}):
        config = load_config()
        assert config["llm"]["provider"] == "env_provider"
        assert config["wallpaper"]["enabled"] is False
