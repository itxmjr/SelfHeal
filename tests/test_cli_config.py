import importlib
import yaml

from typer.testing import CliRunner


def _load_cli_app(monkeypatch, temp_config_dir):
    monkeypatch.setenv("SELFHEAL_CONFIG", str(temp_config_dir / "config"))
    monkeypatch.setenv("SELFHEAL_DATA", str(temp_config_dir / "data"))

    import selfheal.config as config_module
    import selfheal.cli.core as core_module
    import selfheal.cli.main as main_module

    importlib.reload(config_module)
    importlib.reload(core_module)
    main_module = importlib.reload(main_module)
    return main_module.app, temp_config_dir / "config" / "config.yaml"


def test_config_set_get_roundtrip(monkeypatch, temp_config_dir):
    app, config_path = _load_cli_app(monkeypatch, temp_config_dir)
    runner = CliRunner()

    set_result = runner.invoke(app, ["config", "set", "llm.provider", "ollama"])
    assert set_result.exit_code == 0
    assert "Set llm.provider = ollama" in set_result.output

    get_result = runner.invoke(app, ["config", "get", "llm.provider"])
    assert get_result.exit_code == 0
    assert get_result.output.strip() == "ollama"

    with open(config_path) as f:
        saved_config = yaml.safe_load(f)
    assert saved_config["llm"]["provider"] == "ollama"


def test_config_set_nested_numeric_value(monkeypatch, temp_config_dir):
    app, config_path = _load_cli_app(monkeypatch, temp_config_dir)
    runner = CliRunner()

    set_result = runner.invoke(app, ["config", "set", "scoring.weights.task_completion", "55"])
    assert set_result.exit_code == 0

    get_result = runner.invoke(app, ["config", "get", "scoring.weights.task_completion"])
    assert get_result.exit_code == 0
    assert get_result.output.strip() == "55"

    with open(config_path) as f:
        saved_config = yaml.safe_load(f)
    assert saved_config["scoring"]["weights"]["task_completion"] == 55


def test_config_set_rejects_invalid_path(monkeypatch, temp_config_dir):
    app, _ = _load_cli_app(monkeypatch, temp_config_dir)
    runner = CliRunner()

    result = runner.invoke(app, ["config", "set", "llm.unknown", "value"])
    assert result.exit_code == 1
    assert "Invalid config path 'llm.unknown'" in result.output
    assert "llm.provider" in result.output


def test_cli_version_option(monkeypatch, temp_config_dir):
    app, _ = _load_cli_app(monkeypatch, temp_config_dir)
    runner = CliRunner()

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.startswith("selfheal ")
