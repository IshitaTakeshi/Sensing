"""NTRIP configuration loader from a TOML file."""

import tomllib
from pathlib import Path

from sensing.ntrip.config import NTRIPConfig

__all__ = ["load_ntrip_config"]

_CONFIG_PATH = Path("config.toml")


def load_ntrip_config() -> NTRIPConfig | None:
    """Load NTRIP configuration from ``config.toml``.

    Returns ``None`` if the file is absent or has no ``[ntrip]`` section.
    Missing required fields raise ``KeyError`` at startup so the operator
    is alerted immediately rather than failing silently at runtime.

    Returns:
        ``NTRIPConfig`` from the ``[ntrip]`` section, or ``None``.

    Raises:
        KeyError: If a required field is absent from the ``[ntrip]`` section.
    """
    if not _CONFIG_PATH.exists():
        return None
    with _CONFIG_PATH.open("rb") as f:
        data = tomllib.load(f)
    section = data.get("ntrip")
    if section is None:
        return None
    return NTRIPConfig(
        host=section["host"],
        port=section["port"],
        mountpoint=section["mountpoint"],
        serial_device=section["serial_device"],
        username=section.get("username", ""),
        password=section.get("password", ""),
        gga_interval_seconds=section.get("gga_interval_seconds", 10.0),
    )
