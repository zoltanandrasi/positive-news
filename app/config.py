"""Settings: environment variables and the YAML files in the /config folder."""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

DEFAULTS_DIR = Path(__file__).parent / "defaults"
CONFIG_FILES = ("feeds.yaml", "filters.yaml")

# SHA-256 of default config files shipped by earlier versions, which copied them into
# /config. A file in /config that matches one of these was never edited, so it is moved
# aside and the up-to-date built-in default is used instead.
OLD_DEFAULT_HASHES = {
    "2fc36d3bd37ca172a3df09cff4f54d4d0edee67aba9d6682ab8a3da11535ec79",  # feeds.yaml
    "2416fcaa1d5a12e5684a3116a4157969ec8e71ddb7c38ab14f87f44b0c8bdf55",  # feeds.yaml (Hungarian)
    "a97b79972e6451f4de71f75785631ecccb6b25df666317613d5c495be633d034",  # filters.yaml
    "7e5b5b26270442c8b959016258fa4ab149039c339531c5f539ca71078627d06b",  # filters.yaml (Hungarian)
}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        log.warning("Invalid %s value, using default: %s", name, default)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        log.warning("Invalid %s value, using default: %s", name, default)
        return default


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "/data")))
    config_dir: Path = field(default_factory=lambda: Path(os.getenv("CONFIG_DIR", "/config")))
    refresh_interval_hours: float = field(default_factory=lambda: _env_float("REFRESH_INTERVAL_HOURS", 2))
    retention_days: int = field(default_factory=lambda: _env_int("RETENTION_DAYS", 14))
    lead_max_chars: int = field(default_factory=lambda: _env_int("LEAD_MAX_CHARS", 320))
    site_title: str = field(default_factory=lambda: os.getenv("SITE_TITLE", "Jó Hírek"))
    ui_language: str = field(default_factory=lambda: os.getenv("UI_LANGUAGE", "hu").strip().lower())
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "dev"))
    timezone: str = field(default_factory=lambda: os.getenv("TZ", "Europe/Budapest"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "news.db"

    def config_file(self, name: str) -> Path:
        """The user's file in /config if it exists, otherwise the built-in default."""
        custom = self.config_dir / name
        return custom if custom.exists() else DEFAULTS_DIR / name

    def is_custom(self, name: str) -> bool:
        return (self.config_dir / name).exists()

    @property
    def feeds_file(self) -> Path:
        return self.config_file("feeds.yaml")

    @property
    def filters_file(self) -> Path:
        return self.config_file("filters.yaml")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_config(settings: Settings) -> None:
    """Create the folders and refresh the example config files.

    The built-in feeds.yaml and filters.yaml are used (and updated with every new
    version) unless the user puts their own copy in /config. Up-to-date copies are
    written to /config as *.example.yaml to start from.
    """
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    for name in CONFIG_FILES:
        default = DEFAULTS_DIR / name
        custom = settings.config_dir / name
        if custom.exists() and _sha256(custom) in OLD_DEFAULT_HASHES | {_sha256(default)}:
            aside = custom.with_name(name + ".old")
            custom.replace(aside)
            log.info("Unedited old default %s moved to %s; using the built-in list", custom, aside.name)
        example = settings.config_dir / name.replace(".yaml", ".example.yaml")
        try:
            shutil.copy(default, example)
        except OSError as exc:
            log.warning("Could not write %s: %s", example, exc)


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
