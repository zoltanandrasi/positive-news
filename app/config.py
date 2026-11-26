"""Beállítások: környezeti változók és a /config mappa YAML fájljai."""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

DEFAULTS_DIR = Path(__file__).parent / "defaults"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        log.warning("Hibás %s érték, alapértelmezett: %s", name, default)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        log.warning("Hibás %s érték, alapértelmezett: %s", name, default)
        return default


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "/data")))
    config_dir: Path = field(default_factory=lambda: Path(os.getenv("CONFIG_DIR", "/config")))
    refresh_interval_hours: float = field(default_factory=lambda: _env_float("REFRESH_INTERVAL_HOURS", 2))
    retention_days: int = field(default_factory=lambda: _env_int("RETENTION_DAYS", 14))
    lead_max_chars: int = field(default_factory=lambda: _env_int("LEAD_MAX_CHARS", 320))
    site_title: str = field(default_factory=lambda: os.getenv("SITE_TITLE", "Jó Hírek"))
    timezone: str = field(default_factory=lambda: os.getenv("TZ", "Europe/Budapest"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "news.db"

    @property
    def feeds_file(self) -> Path:
        return self.config_dir / "feeds.yaml"

    @property
    def filters_file(self) -> Path:
        return self.config_dir / "filters.yaml"


def ensure_config(settings: Settings) -> None:
    """Létrehozza a mappákat, és bemásolja az alap konfigurációt, ha még nincs."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    for name in ("feeds.yaml", "filters.yaml"):
        target = settings.config_dir / name
        if not target.exists():
            shutil.copy(DEFAULTS_DIR / name, target)
            log.info("Alap konfiguráció létrehozva: %s", target)


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
