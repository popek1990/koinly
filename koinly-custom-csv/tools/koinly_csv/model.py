"""Core data types: an amount of one currency, one Koinly row, and a reported problem."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

_PLAIN_NUMBER = re.compile(r"\d+(\.\d+)?")


class DataError(ValueError):
    """Input that cannot be turned into a correct Koinly row."""


@dataclass(frozen=True)
class Issue:
    """A problem found in the data. Errors stop a build, warnings and notes do not."""

    level: str  # "error", "warning" or "note"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper()}: {self.where}: {self.message}"


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.level == "error" for issue in issues)


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be a Decimal")
        if not self.amount.is_finite() or self.amount <= 0:
            raise DataError(f"amount must be a positive number, got {self.amount} {self.currency}")
        if not self.currency:
            raise DataError("currency is empty")


def format_amount(value: Decimal) -> str:
    """Plain decimal text for Koinly: dot as separator, no exponent, no trailing zeros."""
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def parse_amount(text: str) -> Decimal:
    """Strict parser for amounts in a Koinly file: digits with an optional dot, nothing else."""
    text = text.strip()
    if not _PLAIN_NUMBER.fullmatch(text):
        raise DataError(f"not a plain positive decimal number: {text!r}")
    return Decimal(text)


def parse_decimal(text: str) -> Decimal:
    """Lenient parser for numbers in exchange exports (sign and exponent allowed)."""
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        raise DataError(f"not a number: {text!r}") from None
    if not value.is_finite():
        raise DataError(f"not a finite number: {text!r}")
    return value


@dataclass(frozen=True)
class Row:
    """One row of a Koinly Universal file. Amounts are gross; the fee is separate."""

    time: datetime  # timezone-aware
    sent: Money | None = None
    received: Money | None = None
    fee: Money | None = None
    tag: str = ""
    description: str = ""
    tx_hash: str = ""
    net_worth: Money | None = None  # fiat value of the transacted amount

    def __post_init__(self) -> None:
        if self.time.tzinfo is None or self.time.utcoffset() is None:
            raise DataError("row time must be timezone-aware")
        if self.sent is None and self.received is None:
            raise DataError("a row needs a sent or a received amount")
        if "\n" in self.description or "\r" in self.description:
            raise DataError("description must be a single line")

    @property
    def kind(self) -> str:
        if self.sent and self.received:
            return "trade"
        return "withdrawal" if self.sent else "deposit"


def short_address(address: str) -> str:
    """Shortened address for descriptions, e.g. qzAbCd...WxYz."""
    return address if len(address) <= 13 else f"{address[:6]}...{address[-4:]}"
