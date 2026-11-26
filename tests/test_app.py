from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import fetcher
from app.config import Settings
from app.db import Database
from app.filters import NewsFilter
from app.main import create_app

FIXTURE = (Path(__file__).parent / "fixtures" / "sample.xml").read_bytes()


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("RETENTION_DAYS", "100000")
    s = Settings()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "feeds.yaml").write_text(
        """
categories:
  - { slug: domestic, name: Belföld }
  - { slug: sport, name: Sport }
  - { slug: culture, name: Kultúra }
feeds:
  - { name: Teszt, url: "https://example.hu/rss", category: auto, default_category: domestic }
  - { name: Rossz, url: "https://broken.example/rss", category: sport }
auto_rules:
  sport: { url: ["/sport/"], tags: [sport] }
  culture: { url: ["/kult/"], tags: [kultúra] }
""",
        encoding="utf-8",
    )
    return s


def mock_client():
    def handler(request: httpx.Request):
        if request.url.host == "example.hu":
            return httpx.Response(200, content=FIXTURE)
        if request.url.host == "empty.example":
            return httpx.Response(200, content=b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>')
        return httpx.Response(500)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_filter_stems_words_and_exceptions():
    f = NewsFilter.from_config({
        "block_stems": ["halál", "baleset"],
        "block_words": ["öl"],
        "allow_phrases": ["halálosan jó"],
        "block_title_prefixes": ["Szponzorált"],
    })
    assert f.check("Halálos baleset", "") == "blocked stem: halál"
    assert f.check("Halálosan jó a új lemez", "") is None
    assert f.check("Szép a völgy", "") is None          # "öl" only as a whole word
    assert f.check("Valaki öl", "").startswith("blocked word")
    assert f.check("Szponzorált: nyaralás", "").startswith("title prefix")


def test_make_lead_cleans_and_truncates():
    assert fetcher.make_lead("<p>Szia &amp; helló</p>", 100) == "Szia & helló"
    long = "Első mondat itt van. " + "szó " * 100
    assert fetcher.make_lead(long, 60).endswith("…")
    assert fetcher.make_lead("A szöveg. A bejegyzés X első megjelenése: Y.", 100) == "A szöveg."


def test_run_once_stores_filters_and_categorizes(settings):
    db = Database(settings.db_path)
    result = fetcher.run_once(settings, db, client=mock_client())
    assert result["ok"] == 1 and result["feeds"] == 2
    assert result["added"] == 3 and result["blocked"] == 1

    visible = {a["title"]: a for a in db.latest(limit=50)}
    assert set(visible) == {
        "Aranyérmet nyert a magyar kajakos az Európa-bajnokságon",
        "Új kiállítás nyílik a Nemzeti Galériában",
        "Önkéntesek ültettek fát a városligetben",
    }
    kajak = visible["Aranyérmet nyert a magyar kajakos az Európa-bajnokságon"]
    assert kajak["category"] == "sport"
    assert kajak["image_url"] == "https://example.hu/img/kajak.jpg"
    assert "&" in kajak["lead"] and "<" not in kajak["lead"]
    kiall = visible["Új kiállítás nyílik a Nemzeti Galériában"]
    assert kiall["category"] == "culture"
    assert kiall["lead"] == "A tárlat a magyar impresszionizmust mutatja be."
    assert kiall["image_url"] == "https://example.hu/img/kiallitas.jpg"
    assert visible["Önkéntesek ültettek fát a városligetben"]["category"] == "domestic"

    statuses = {s["name"]: s for s in db.feed_statuses()}
    assert statuses["Teszt"]["ok"] == 1
    assert statuses["Rossz"]["ok"] == 0 and "500" in statuses["Rossz"]["error"]

    # a second run does not create duplicates
    again = fetcher.run_once(settings, db, client=mock_client())
    assert again["added"] == 0 and again["blocked"] == 0


def test_web_pages(settings):
    db = Database(settings.db_path)
    fetcher.run_once(settings, db, client=mock_client())
    app = create_app(settings, start_scheduler=False)
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "Aranyérmet nyert" in r.text and "Halálos baleset" not in r.text
        r = client.get("/category/sport")
        assert r.status_code == 200 and "kajakos" in r.text and "kiállítás" not in r.text
        assert client.get("/category/missing").status_code == 404
        r = client.get("/status")
        assert r.status_code == 200 and "Halálos baleset" in r.text and "blocked stem: halál" in r.text
        assert client.get("/healthz").text == "ok"
        assert client.get("/static/style.css").status_code == 200


def test_default_config_is_created(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "c"))
    s = Settings()
    app = create_app(s, start_scheduler=False)
    # built-in lists are used; only example copies are written
    assert not (tmp_path / "c" / "feeds.yaml").exists()
    assert (tmp_path / "c" / "feeds.example.yaml").exists()
    assert (tmp_path / "c" / "filters.example.yaml").exists()
    assert s.feeds_file.parent.name == "defaults"
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200 and "Még nincsenek hírek" in r.text


def test_english_ui(settings, monkeypatch):
    monkeypatch.setenv("UI_LANGUAGE", "en")
    s = Settings()
    db = Database(s.db_path)
    fetcher.run_once(s, db, client=mock_client())
    app = create_app(s, start_scheduler=False)
    with TestClient(app) as client:
        r = client.get("/")
        assert 'lang="en"' in r.text and "Latest" in r.text
        assert "Aranyérmet nyert" in r.text  # the news itself stays Hungarian


def test_empty_feed_is_reported_as_error(settings):
    cfg = settings.feeds_file.read_text(encoding="utf-8")
    settings.feeds_file.write_text(cfg.replace(
        "auto_rules:", '  - { name: Ures, url: "https://empty.example/rss", category: sport }\nauto_rules:'), encoding="utf-8")
    db = Database(settings.db_path)
    fetcher.run_once(settings, db, client=mock_client())
    status = {s["name"]: s for s in db.feed_statuses()}["Ures"]
    assert status["ok"] == 0 and "no articles" in status["error"]


def test_unedited_old_default_is_moved_aside(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "c"))
    (tmp_path / "c").mkdir()
    from app.config import DEFAULTS_DIR, ensure_config
    # an unedited copy of the current default counts as "not customized"
    (tmp_path / "c" / "filters.yaml").write_bytes((DEFAULTS_DIR / "filters.yaml").read_bytes())
    # an edited file is kept
    (tmp_path / "c" / "feeds.yaml").write_text("categories: []\nfeeds: []\n", encoding="utf-8")
    s = Settings()
    ensure_config(s)
    assert not (tmp_path / "c" / "filters.yaml").exists()
    assert (tmp_path / "c" / "filters.yaml.old").exists()
    assert s.filters_file.parent.name == "defaults"
    assert s.feeds_file == tmp_path / "c" / "feeds.yaml"


def test_status_shows_version(settings, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "2026-11-26-abc1234")
    app = create_app(Settings(), start_scheduler=False)
    with TestClient(app) as client:
        r = client.get("/status")
        assert "2026-11-26-abc1234" in r.text and "saját (config mappa)" in r.text
