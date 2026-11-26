"""Download, parse, filter and store RSS feeds."""
from __future__ import annotations

import calendar
import html
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import httpx

from .config import Settings, ensure_config, load_yaml
from .db import Database, iso, utcnow
from .filters import NewsFilter

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; PositiveNews/1.0; self-hosted RSS reader)"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
# Typical RSS trailer text that is cut from the lead.
# Hungarian sources use "A bejegyzés ... első megjelenése" (WordPress "The post ... appeared
# first on") and "Tovább olvasom" ("Read more"), so those patterns stay in Hungarian.
_BOILERPLATE_RE = re.compile(
    r"(A bejegyzés .*? első megjelenése: .*$|The post .*? appeared first on .*$|"
    r"Tovább(?: olvasom)?\s*(?:»|›|&raquo;)?\s*$|\[(?:…|\.\.\.)\]\s*$)",
    re.IGNORECASE | re.DOTALL,
)

_run_lock = threading.Lock()


# --- helpers -----------------------------------------------------------------
def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    text = _BOILERPLATE_RE.sub("", text).strip()
    return text


def make_lead(raw: str | None, max_chars: int) -> str:
    text = clean_text(raw)
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Cut at a sentence end if there is one in the second half.
    sentence_end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if sentence_end > max_chars // 2:
        return cut[: sentence_end + 1]
    return cut.rsplit(" ", 1)[0].rstrip(",;:–- ") + "…"


def title_key(title: str) -> str:
    """Normalized title, used to detect duplicates."""
    return re.sub(r"[^\w]+", " ", title.lower()).strip()


def entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
            except (OverflowError, ValueError):
                continue
    return None


def entry_image(entry) -> str | None:
    for key in ("media_thumbnail", "media_content"):
        for m in entry.get(key) or []:
            url = m.get("url")
            if url and (key == "media_thumbnail" or str(m.get("medium", "image")) == "image"
                        or str(m.get("type", "")).startswith("image")):
                return url
    for enc in entry.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    for field in ("summary", "description"):
        m = _IMG_RE.search(entry.get(field) or "")
        if m:
            return m.group(1)
    content = entry.get("content") or []
    if content:
        m = _IMG_RE.search(content[0].get("value") or "")
        if m:
            return m.group(1)
    return None


def entry_tags(entry) -> list[str]:
    return [str(t.get("term", "")).lower() for t in (entry.get("tags") or []) if t.get("term")]


def resolve_category(feed: dict, link: str, tags: list[str], auto_rules: dict, valid: set[str]) -> str:
    cat = str(feed.get("category") or "auto")
    if cat != "auto":
        return cat if cat in valid else feed.get("default_category") or next(iter(valid))
    path = urlparse(link).path.lower()
    for slug, rule in (auto_rules or {}).items():
        if slug not in valid:
            continue
        rule = rule or {}
        if any(str(p).lower() in path for p in rule.get("url") or []):
            return slug
        rule_tags = [str(t).lower() for t in rule.get("tags") or []]
        if any(rt == t or rt in t for t in tags for rt in rule_tags):
            return slug
    default = feed.get("default_category")
    return default if default in valid else next(iter(valid))


# --- main flow ---------------------------------------------------------------
def load_config(settings: Settings) -> tuple[list[dict], list[dict], dict, NewsFilter]:
    ensure_config(settings)
    feeds_cfg = load_yaml(settings.feeds_file)
    filters_cfg = load_yaml(settings.filters_file)
    categories = feeds_cfg.get("categories") or []
    feeds = [f for f in (feeds_cfg.get("feeds") or []) if f.get("url") and f.get("enabled", True)]
    return categories, feeds, feeds_cfg.get("auto_rules") or {}, NewsFilter.from_config(filters_cfg)


def process_feed(con, db: Database, settings: Settings, feed: dict, content: bytes,
                 auto_rules: dict, valid: set[str], news_filter: NewsFilter) -> dict:
    parsed = feedparser.parse(content)
    if not parsed.entries:
        if parsed.bozo:
            raise ValueError(f"Could not parse RSS: {parsed.get('bozo_exception')}")
        raise ValueError("The feed has no articles (wrong URL, or not an article feed)")

    now = utcnow()
    oldest = now - timedelta(days=settings.retention_days)
    items = added = blocked = 0
    for entry in parsed.entries:
        items += 1
        link = (entry.get("link") or "").strip()
        title = clean_text(entry.get("title"))
        if not link or not title:
            continue
        published = entry_datetime(entry) or now
        if published < oldest:
            continue
        if published > now + timedelta(hours=1):
            published = now
        key = title_key(title)
        if db.has_link_or_title(con, link, key):
            continue

        raw_summary = entry.get("summary") or entry.get("description") or ""
        lead = make_lead(raw_summary, settings.lead_max_chars)
        reason = news_filter.check(title, lead)
        db.insert_article(con, {
            "link": link,
            "title": title,
            "title_key": key,
            "lead": lead,
            "image_url": entry_image(entry),
            "source": feed.get("name") or urlparse(feed["url"]).netloc,
            "category": resolve_category(feed, link, entry_tags(entry), auto_rules, valid),
            "published_at": iso(published),
            "fetched_at": iso(now),
            "blocked_by": reason,
        })
        if reason:
            blocked += 1
        else:
            added += 1
    return {"items": items, "added": added, "blocked": blocked}


def run_once(settings: Settings, db: Database, client: httpx.Client | None = None) -> dict:
    """Run one full refresh. If one is already running, this call is skipped."""
    if not _run_lock.acquire(blocking=False):
        log.info("Refresh already running, skipped.")
        return {"skipped": True}
    try:
        return _run(settings, db, client)
    finally:
        _run_lock.release()


def _run(settings: Settings, db: Database, client: httpx.Client | None) -> dict:
    categories, feeds, auto_rules, news_filter = load_config(settings)
    valid = [c["slug"] for c in categories if c.get("slug")] or ["other"]
    valid_set = dict.fromkeys(valid)  # insertion-ordered "set"
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})

    totals = {"feeds": len(feeds), "ok": 0, "added": 0, "blocked": 0}
    log.info("Refresh started: %d feeds", len(feeds))
    try:
        with db.connect() as con:
            for feed in feeds:
                status = {"url": feed["url"], "name": feed.get("name") or feed["url"],
                          "last_run_at": iso(utcnow()), "ok": 0, "items": 0, "added": 0,
                          "blocked": 0, "error": None}
                try:
                    resp = client.get(feed["url"])
                    resp.raise_for_status()
                    result = process_feed(con, db, settings, feed, resp.content,
                                          auto_rules, valid_set, news_filter)
                    status.update(result, ok=1)
                    totals["ok"] += 1
                    totals["added"] += result["added"]
                    totals["blocked"] += result["blocked"]
                    log.info("  %s: %d items, %d new, %d blocked", status["name"],
                             result["items"], result["added"], result["blocked"])
                except Exception as exc:  # one broken feed must not stop the others
                    status["error"] = f"{type(exc).__name__}: {exc}"[:500]
                    log.warning("  %s: ERROR %s", status["name"], status["error"])
                db.save_feed_status(con, status)
                con.commit()

            urls = [f["url"] for f in feeds]
            if urls:
                con.execute(f"DELETE FROM feed_status WHERE url NOT IN ({','.join('?' * len(urls))})", urls)
            else:
                con.execute("DELETE FROM feed_status")
            db.set_meta(con, "last_run_at", iso(utcnow()))
    finally:
        if own_client:
            client.close()

    purged = db.purge_older_than(settings.retention_days)
    log.info("Refresh done: %d/%d feeds OK, %d new articles, %d blocked, %d old deleted",
             totals["ok"], totals["feeds"], totals["added"], totals["blocked"], purged)
    totals["purged"] = purged
    return totals


if __name__ == "__main__":  # manual run: python -m app.fetcher
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = Settings()
    print(run_once(s, Database(s.db_path)))
