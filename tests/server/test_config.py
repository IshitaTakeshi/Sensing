"""Tests for server.config.load_ntrip_config."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sensing.ntrip.config import NTRIPConfig
from server.config import load_ntrip_config


def test_file_absent_returns_none(tmp_path: Path) -> None:
    with patch("server.config._CONFIG_PATH", tmp_path / "config.toml"):
        assert load_ntrip_config() is None


def test_no_ntrip_section_returns_none(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[other]\nkey = 'value'\n")
    with patch("server.config._CONFIG_PATH", config):
        assert load_ntrip_config() is None


def test_valid_section_returns_config(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[ntrip]\n"
        'host = "ntrip.example.com"\n'
        "port = 2101\n"
        'mountpoint = "NEAR00"\n'
        'serial_device = "/dev/ttyAMA5"\n'
    )
    with patch("server.config._CONFIG_PATH", config):
        result = load_ntrip_config()
    assert result == NTRIPConfig(
        host="ntrip.example.com",
        port=2101,
        mountpoint="NEAR00",
        serial_device="/dev/ttyAMA5",
    )


def test_missing_required_field_raises_key_error(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[ntrip]\n"
        'host = "ntrip.example.com"\n'
        "port = 2101\n"
    )
    with patch("server.config._CONFIG_PATH", config), pytest.raises(KeyError):
        load_ntrip_config()
