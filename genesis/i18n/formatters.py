"""RADUI Internationalization (i18n): Translation catalogs and locale-aware formatters."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import date, datetime
import decimal
import re
from typing import Any

_CURRENT_LOCALE: ContextVar[str] = ContextVar("gx_locale", default="en")


class Translator:
    """Translation catalog manager supporting variable substitution and fallback locales."""

    def __init__(self, default_locale: str = "en", fallback_locale: str = "en") -> None:
        self.default_locale = default_locale
        self.fallback_locale = fallback_locale
        self._catalogs: dict[str, dict[str, str]] = {}

    def load_catalog(self, locale: str, entries: dict[str, str]) -> None:
        """Register or extend translations for a specific locale (e.g. 'en', 'es', 'ar')."""
        norm = locale.lower().replace("-", "_")
        if norm not in self._catalogs:
            self._catalogs[norm] = {}
        self._catalogs[norm].update(entries)

    def t(self, key: str, locale: str | None = None, **kwargs: Any) -> str:
        """Translate a message key for the target locale with keyword interpolation."""
        target = (locale or _CURRENT_LOCALE.get()).lower().replace("-", "_")
        lang_only = target.split("_")[0]

        # 1. Exact match
        text = self._catalogs.get(target, {}).get(key)
        # 2. Language-only match (e.g. 'en_US' -> 'en')
        if text is None:
            text = self._catalogs.get(lang_only, {}).get(key)
        # 3. Fallback locale
        if text is None:
            text = self._catalogs.get(self.fallback_locale, {}).get(key, key)

        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text


_GLOBAL_TRANSLATOR = Translator()


def t(key: str, locale: str | None = None, **kwargs: Any) -> str:
    """Global translation helper."""
    return _GLOBAL_TRANSLATOR.t(key, locale=locale, **kwargs)


def set_locale(locale: str):
    """Set the current context's locale."""
    return _CURRENT_LOCALE.set(locale)


def get_locale() -> str:
    """Get the current context's locale."""
    return _CURRENT_LOCALE.get()


def format_number(val: float | int, locale: str | None = None) -> str:
    """Format a numeric value with standard thousand grouping."""
    loc = (locale or get_locale()).lower()
    is_float = isinstance(val, float) and not val.is_integer()
    raw = f"{val:,.2f}" if is_float else f"{int(val):,}"

    if loc.startswith("de") or loc.startswith("es"):
        # German & Spanish convention: period for thousands, comma for decimals (e.g. 1.250.000,50)
        parts = raw.split(".")
        int_part = parts[0].replace(",", ".")
        return f"{int_part},{parts[1]}" if len(parts) > 1 else int_part
    elif loc.startswith(("fr", "ru")):
        # French & Russian convention: non-breaking space for thousands, comma for decimals
        parts = raw.split(".")
        int_part = parts[0].replace(",", " ")
        return f"{int_part},{parts[1]}" if len(parts) > 1 else int_part
    return raw


def format_currency(val: float | int, currency: str = "USD", locale: str | None = None) -> str:
    """Format currency values with standard ISO code or symbol."""
    formatted_num = format_number(val, locale=locale)
    symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
        "INR": "₹",
    }
    symbol = symbols.get(currency.upper(), currency.upper() + " ")
    return f"{symbol}{formatted_num}"


def format_date(dt: date | datetime | str, format: str = "medium", locale: str | None = None) -> str:
    """Format a date or datetime object into an ISO or localized string."""
    loc = (locale or get_locale()).lower()
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt

    if format == "short":
        if loc.startswith("de"):
            return dt.strftime("%d.%m.%Y")
        elif loc.startswith("fr"):
            return dt.strftime("%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    elif format == "long":
        return dt.strftime("%B %d, %Y")
    elif format == "time":
        return dt.strftime("%H:%M:%S")
    return dt.strftime("%b %d, %Y")
