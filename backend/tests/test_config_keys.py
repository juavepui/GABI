from gabi import config


def test_tiingo_key_is_saved_locally_and_env_takes_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "TIINGO_KEY_PATH", tmp_path / "tiingo_api_key.txt")
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    assert config.load_tiingo_key() is None
    config.save_tiingo_key("  abc123 \n")
    assert config.load_tiingo_key() == "abc123"
    monkeypatch.setenv("TIINGO_API_KEY", "from-env")
    assert config.load_tiingo_key() == "from-env"


def test_nasdaq_data_link_key_is_saved_locally_and_env_takes_priority(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "NASDAQ_DATA_LINK_KEY_PATH", tmp_path / "ndl.txt")
    monkeypatch.delenv("NASDAQ_DATA_LINK_API_KEY", raising=False)
    assert config.load_nasdaq_data_link_key() is None
    config.save_nasdaq_data_link_key("  xyz  ")
    assert config.load_nasdaq_data_link_key() == "xyz"
    monkeypatch.setenv("NASDAQ_DATA_LINK_API_KEY", "env-key")
    assert config.load_nasdaq_data_link_key() == "env-key"
