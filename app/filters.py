"""Kulcsszavas szűrés a negatív hírek kiszűrésére."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class NewsFilter:
    block_stems: list[str]
    block_words: list[str]
    allow_phrases: list[str]
    block_title_prefixes: list[str]

    @classmethod
    def from_config(cls, cfg: dict) -> "NewsFilter":
        def norm(key: str) -> list[str]:
            return [str(x).strip().lower() for x in (cfg.get(key) or []) if str(x).strip()]

        return cls(
            block_stems=norm("block_stems"),
            block_words=norm("block_words"),
            allow_phrases=norm("allow_phrases"),
            block_title_prefixes=norm("block_title_prefixes"),
        )

    def __post_init__(self) -> None:
        self._word_re = None
        if self.block_words:
            alts = "|".join(re.escape(w) for w in sorted(self.block_words, key=len, reverse=True))
            # \w Unicode-os, így az ékezetes betűk is szókaraktereknek számítanak.
            self._word_re = re.compile(rf"(?<!\w)({alts})(?!\w)", re.IGNORECASE)

    def check(self, title: str, lead: str) -> str | None:
        """Visszaadja a kiszűrés okát, vagy None-t, ha a hír megjelenhet."""
        t = (title or "").strip().lower()
        text = f"{t}\n{(lead or '').lower()}"

        for prefix in self.block_title_prefixes:
            if t.startswith(prefix):
                return f"cím eleje: {prefix}"

        if any(p in text for p in self.allow_phrases):
            return None

        for stem in self.block_stems:
            if stem in text:
                return f"tiltott szótő: {stem}"

        if self._word_re:
            m = self._word_re.search(text)
            if m:
                return f"tiltott szó: {m.group(1).lower()}"
        return None
