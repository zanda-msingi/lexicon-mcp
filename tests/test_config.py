"""Tests for the TOML config loader."""

from pathlib import Path

from lexicon_mcp.config import Config, load_config


def test_defaults_when_no_file(tmp_path: Path):
    cfg = load_config(tmp_path / "does-not-exist.toml")
    assert cfg == Config()
    assert cfg.base_url == "http://localhost:48624"
    assert cfg.log_level == "info"


def test_loads_values_from_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[lexicon]\nbase_url = "http://127.0.0.1:9999"\n[server]\nlog_level = "debug"\n')
    cfg = load_config(p)
    assert cfg.base_url == "http://127.0.0.1:9999"
    assert cfg.log_level == "debug"


def test_partial_toml_falls_back_to_defaults(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[lexicon]\nbase_url = "http://elsewhere:1234"\n')
    cfg = load_config(p)
    assert cfg.base_url == "http://elsewhere:1234"
    assert cfg.log_level == "info"  # default preserved
