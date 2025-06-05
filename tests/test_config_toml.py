import importlib
import os
from pathlib import Path

def test_config_from_toml(tmp_path, monkeypatch):
    cfg = tmp_path / "conf.toml"
    cfg.write_text("""
INLINE_TAGS = ["b", "i", "u"]
ID_LENGTH = 8
LOG_LEVEL = "DEBUG"
""")
    monkeypatch.setenv("DITA_PARSER_CONFIG", str(cfg))
    import config
    importlib.reload(config)
    assert config.ID_LENGTH == 8
    assert config.LOG_LEVEL == "DEBUG"
    assert "b" in config.INLINE_TAGS
    monkeypatch.delenv("DITA_PARSER_CONFIG")
    importlib.reload(config)
