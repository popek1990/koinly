"""Predict which withdrawals and deposits Koinly will merge into transfers.

Koinly's auto-matching rules, help article 9490024 (checked 2026-09-29):
- likeness: same asset/currency;
- interval: within 12 hours of each other;
- chronology: the withdrawal happens before the deposit;
- amount: the deposit is equal to or smaller than the withdrawal;
- difference: the deposit is at most 20% smaller than the withdrawal;
- hash: the same transaction hash, or at least one side has no hash.

A leg without a pair becomes a "broken transfer" (article 9490066): the withdrawal is
treated as a sale at market price and the deposit as a purchase at market price.
This module only predicts; Koinly has the final word.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from .model import Row, format_amount

MAX_INTERVAL = timedelta(hours=12)
MAX_SHORTFALL = Decimal("0.20")


@dataclass(frozen=True)
class Leg:
    """One side of a possible transfer."""

    wallet: str
    direction: str  # "out" (withdrawal) or "in" (deposit)
    time: datetime
    amount: Decimal
    currency: str
    tx_hash: str = ""
    label: str = ""

    def __str__(self) -> str:
        kind = "withdrawal" if self.direction == "out" else "deposit"
        text = f"{self.wallet} {kind} {format_amount(self.amount)} {self.currency} at {self.time:%Y-%m-%d %H:%M:%S} UTC"
        return f"{text} ({self.label})" if self.label else text


@dataclass
class MatchResult:
    pairs: list[tuple[Leg, Leg]] = field(default_factory=list)
    unmatched: list[Leg] = field(default_factory=list)


def legs_from_rows(wallet: str, rows: list[Row]) -> list[Leg]:
    """Untagged deposits and withdrawals. Tagged rows (airdrop, cost...) are not transfers."""
    legs = []
    for row in rows:
        if row.tag or row.kind == "trade":
            continue
        money = row.sent or row.received
        legs.append(Leg(wallet, "out" if row.sent else "in", row.time, money.amount, money.currency,
                        row.tx_hash, row.description))
    return legs


def _format_delta(delta: timedelta) -> str:
    seconds = int(abs(delta).total_seconds())
    hours, rest = divmod(seconds, 3600)
    return f"{hours}h {rest // 60:02d}m" if hours else f"{rest // 60}m {rest % 60:02d}s"


def rule_failures(out: Leg, inc: Leg) -> list[str]:
    """Why Koinly would not merge this withdrawal with this deposit (empty list = it would)."""
    reasons = []
    if out.currency != inc.currency:
        reasons.append(f"different currency ({out.currency} vs {inc.currency})")
    gap = inc.time - out.time
    if gap < timedelta(0):
        text = f"the deposit is {_format_delta(gap)} before the withdrawal"
        remainder = abs(gap).total_seconds() % 3600
        if abs(gap) >= timedelta(minutes=45) and min(remainder, 3600 - remainder) <= 900:
            text += " (close to a whole number of hours: probably a file imported in the wrong time zone)"
        reasons.append(text)
    elif gap > MAX_INTERVAL:
        reasons.append(f"more than 12 hours apart ({_format_delta(gap)})")
    if inc.amount > out.amount:
        reasons.append(f"the deposit ({format_amount(inc.amount)}) is larger than the withdrawal "
                       f"({format_amount(out.amount)})")
    elif inc.amount < out.amount * (1 - MAX_SHORTFALL):
        reasons.append("the deposit is more than 20% smaller than the withdrawal")
    if out.tx_hash and inc.tx_hash and out.tx_hash != inc.tx_hash:
        reasons.append("different transaction hashes")
    return reasons


def match(legs: list[Leg]) -> MatchResult:
    """Pair withdrawals with deposits in time order; a matching hash wins, then the shortest gap."""
    result = MatchResult()
    deposits = [leg for leg in legs if leg.direction == "in"]
    used: set[int] = set()
    for out in sorted((leg for leg in legs if leg.direction == "out"), key=lambda leg: leg.time):
        candidates = [
            (index, inc) for index, inc in enumerate(deposits)
            if index not in used and inc.wallet != out.wallet and not rule_failures(out, inc)
        ]
        if not candidates:
            result.unmatched.append(out)
            continue
        index, inc = min(candidates, key=lambda item: (
            not (out.tx_hash and item[1].tx_hash == out.tx_hash), item[1].time - out.time))
        used.add(index)
        result.pairs.append((out, inc))
    result.unmatched += [inc for index, inc in enumerate(deposits) if index not in used]
    result.unmatched.sort(key=lambda leg: leg.time)
    return result


def near_misses(leg: Leg, legs: list[Leg]) -> list[tuple[Leg, list[str]]]:
    """Legs in other wallets that look like the other side of `leg` but break a rule."""
    found = []
    for other in legs:
        if other.wallet == leg.wallet or other.direction == leg.direction:
            continue
        same_hash = bool(leg.tx_hash) and other.tx_hash == leg.tx_hash
        if leg.tx_hash and other.tx_hash and not same_hash:
            continue  # two different transactions, not a near miss
        similar = (other.currency == leg.currency and abs(other.time - leg.time) <= timedelta(hours=26)
                   and other.amount > 0 and abs(other.amount - leg.amount) <= leg.amount * MAX_SHORTFALL)
        if not (same_hash or similar):
            continue
        out, inc = (leg, other) if leg.direction == "out" else (other, leg)
        reasons = rule_failures(out, inc)
        if reasons:
            found.append((other, reasons))
    return found
