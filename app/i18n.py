"""Website text. The UI language is chosen with the UI_LANGUAGE setting (hu or en)."""
from __future__ import annotations

from datetime import datetime

STRINGS: dict[str, dict[str, str]] = {
    "hu": {
        "html_lang": "hu",
        "tagline": "Pozitív és semleges hírek, egy helyen",
        "home": "Címlap",
        "latest": "Legfrissebb",
        "more_in": "További hírek: {name} →",
        "no_news_title": "Még nincsenek hírek",
        "no_news_body": "Az első frissítés az indulás után néhány másodperccel lefut. "
                        "Pár perc múlva frissítsd az oldalt, vagy nézd meg az állapotoldalt.",
        "empty_category": "Ebben a rovatban még nincs hír.",
        "newer": "← Újabbak",
        "older": "Régebbiek →",
        "footer_last_refresh": "Utolsó frissítés",
        "footer_note": "A címek és leadek a források RSS-csatornáiból származnak, "
                       "a teljes cikk a forrásoldalon olvasható.",
        "status": "Állapot",
        "status_visible": "Megjelenő hírek",
        "status_refresh": "Frissítés",
        "status_every_hours": "{n} óránként",
        "status_retention": "Megőrzés",
        "status_days": "{n} nap",
        "status_feeds": "Források",
        "status_col_feed": "Forrás",
        "status_col_state": "Állapot",
        "status_col_items": "Elemek",
        "status_col_new": "Új",
        "status_col_blocked": "Kiszűrve",
        "status_col_last_run": "Utoljára",
        "status_ok": "rendben",
        "status_error": "hiba",
        "status_no_run": "Még nem volt frissítés.",
        "status_blocked_title": "Legutóbb kiszűrt hírek",
        "status_blocked_hint": "Ha egy ártalmatlan hír rossz okból esett ki, vedd ki vagy pontosítsd "
                               "a szót a config/filters.yaml fájlban.",
        "status_col_title": "Cím",
        "status_col_reason": "Ok",
        "status_no_blocked": "Nincs kiszűrt hír.",
        "not_found": "Ez az oldal nem található",
        "back_home": "Vissza a címlapra",
        "never": "még nem volt",
        "today": "ma",
        "yesterday": "tegnap",
    },
    "en": {
        "html_lang": "en",
        "tagline": "Positive and neutral news in one place",
        "home": "Home",
        "latest": "Latest",
        "more_in": "More in {name} →",
        "no_news_title": "No news yet",
        "no_news_body": "The first refresh runs a few seconds after startup. "
                        "Reload this page in a few minutes, or check the status page.",
        "empty_category": "No news in this category yet.",
        "newer": "← Newer",
        "older": "Older →",
        "footer_last_refresh": "Last refresh",
        "footer_note": "Titles and leads come from the sources' RSS feeds; "
                       "read the full article on the source site.",
        "status": "Status",
        "status_visible": "Visible articles",
        "status_refresh": "Refresh",
        "status_every_hours": "every {n} hours",
        "status_retention": "Retention",
        "status_days": "{n} days",
        "status_feeds": "Feeds",
        "status_col_feed": "Feed",
        "status_col_state": "State",
        "status_col_items": "Items",
        "status_col_new": "New",
        "status_col_blocked": "Blocked",
        "status_col_last_run": "Last run",
        "status_ok": "OK",
        "status_error": "error",
        "status_no_run": "No refresh has run yet.",
        "status_blocked_title": "Recently blocked articles",
        "status_blocked_hint": "If a harmless article was blocked for the wrong reason, remove or refine "
                               "that term in config/filters.yaml.",
        "status_col_title": "Title",
        "status_col_reason": "Reason",
        "status_no_blocked": "No blocked articles.",
        "not_found": "Page not found",
        "back_home": "Back to the home page",
        "never": "never",
        "today": "today",
        "yesterday": "yesterday",
    },
}

MONTHS = {
    "hu": ["január", "február", "március", "április", "május", "június", "július",
           "augusztus", "szeptember", "október", "november", "december"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}


def get_strings(lang: str) -> dict[str, str]:
    return STRINGS.get(lang, STRINGS["hu"])


def format_date(dt: datetime, lang: str) -> str:
    months = MONTHS.get(lang, MONTHS["hu"])
    if lang == "en":
        return f"{months[dt.month - 1]} {dt.day}, {dt:%H:%M}"
    return f"{months[dt.month - 1]} {dt.day}. {dt:%H:%M}"
