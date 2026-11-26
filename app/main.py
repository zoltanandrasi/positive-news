"""Web server and scheduler."""
from __future__ import annotations

import logging
import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings, ensure_config, load_yaml
from .db import Database
from .fetcher import run_once
from .i18n import format_date, get_strings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("positive-news")

BASE_DIR = Path(__file__).parent
PAGE_SIZE = 30
FRONT_PER_CATEGORY = 6



def create_app(settings: Settings | None = None, start_scheduler: bool = True) -> FastAPI:
    settings = settings or Settings()
    ensure_config(settings)
    db = Database(settings.db_path)
    try:
        tz = ZoneInfo(settings.timezone)
    except Exception:
        tz = ZoneInfo("Europe/Budapest")

    lang = settings.ui_language
    t = get_strings(lang)
    scheduler = BackgroundScheduler(timezone=tz)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_scheduler:
            minutes = max(5, int(round(settings.refresh_interval_hours * 60)))
            scheduler.add_job(run_once, "interval", minutes=minutes, args=[settings, db],
                              id="refresh", max_instances=1, coalesce=True,
                              next_run_time=datetime.now(tz) + timedelta(seconds=5))
            scheduler.start()
            log.info("Scheduler started, refreshing every %d minutes", minutes)
        yield
        if scheduler.running:
            scheduler.shutdown(wait=False)

    app = FastAPI(title=settings.site_title, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    def parse_utc(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    def fmt_time(value: str | None) -> str:
        dt = parse_utc(value)
        if not dt:
            return t["never"]
        local = dt.astimezone(tz)
        today = datetime.now(tz).date()
        if local.date() == today:
            return f"{t['today']} {local:%H:%M}"
        if local.date() == today - timedelta(days=1):
            return f"{t['yesterday']} {local:%H:%M}"
        return format_date(local, lang)

    templates.env.filters["hutime"] = fmt_time

    def categories() -> list[dict]:
        cfg = load_yaml(settings.feeds_file)
        return [c for c in (cfg.get("categories") or []) if c.get("slug")]

    def render(request: Request, name: str, **ctx) -> HTMLResponse:
        cats = categories()
        ctx.setdefault("active", None)
        return templates.TemplateResponse(request, name, {
            "site_title": settings.site_title,
            "t": t,
            "categories": cats,
            "category_names": {c["slug"]: c.get("name", c["slug"]) for c in cats},
            "last_run": db.get_meta("last_run_at"),
            **ctx,
        })

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        sections = []
        for c in categories():
            items = db.latest(c["slug"], limit=FRONT_PER_CATEGORY)
            if items:
                sections.append({"category": c, "articles": items})
        return render(request, "index.html", top=db.latest(limit=5), sections=sections)

    @app.get("/category/{slug}", response_class=HTMLResponse)
    def category(request: Request, slug: str, page: int = 1):
        cat = next((c for c in categories() if c["slug"] == slug), None)
        if not cat:
            raise HTTPException(404)
        total = db.count(slug)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        page = min(max(1, page), pages)
        items = db.latest(slug, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
        return render(request, "category.html", category=cat, articles=items,
                      page=page, pages=pages, active=slug)

    @app.get("/status", response_class=HTMLResponse)
    def status(request: Request):
        return render(request, "status.html", feeds=db.feed_statuses(), blocked=db.blocked(100),
                      total=db.count(), interval=settings.refresh_interval_hours,
                      retention=settings.retention_days, version=settings.app_version,
                      feeds_custom=settings.is_custom("feeds.yaml"),
                      filters_custom=settings.is_custom("filters.yaml"))

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz():
        return "ok"

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        resp = render(request, "404.html")
        resp.status_code = 404
        return resp

    return app

