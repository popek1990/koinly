"""Currency notation accepted by Koinly CSV imports.

Koinly help article 9489976, section "Extended symbol notation" (checked 2026-09-29):
- a plain symbol, e.g. BTC (Koinly picks the most popular token with that symbol);
- a contract address with an optional chain: SYMBOL:CONTRACT_ADDRESS or SYMBOL:CONTRACT_ADDRESS:BLOCKCHAIN;
- Koinly's internal ID from the Markets page: ID:18431515.
"""
from __future__ import annotations

import re

_SYMBOL = r"[A-Za-z0-9][A-Za-z0-9.$_-]{0,31}"
_PLAIN = re.compile(_SYMBOL)
_KOINLY_ID = re.compile(r"ID:\d+")
_CONTRACT = re.compile(rf"{_SYMBOL}:[A-Za-z0-9]{{8,}}(:[A-Za-z0-9]{{1,16}})?")
_FIAT = re.compile(r"[A-Z]{3}")


def notation_problem(text: str) -> str | None:
    """Return why `text` is not a valid Koinly currency, or None when it is valid."""
    if not text:
        return "currency is empty"
    if text != text.strip():
        return f"currency {text!r} has leading or trailing spaces"
    if text.upper().startswith("ID:"):
        return None if _KOINLY_ID.fullmatch(text) else f"{text!r} is not in the form ID:<digits>"
    if ":" in text:
        if _CONTRACT.fullmatch(text):
            return None
        return f"{text!r} is not in the form SYMBOL:CONTRACT_ADDRESS[:BLOCKCHAIN]"
    return None if _PLAIN.fullmatch(text) else f"{text!r} is not a plain token symbol"


def is_plain_symbol(text: str) -> bool:
    return ":" not in text


def looks_like_fiat(text: str) -> bool:
    """Net Worth Currency accepts fiat only (USD, EUR, GBP...)."""
    return bool(_FIAT.fullmatch(text))
