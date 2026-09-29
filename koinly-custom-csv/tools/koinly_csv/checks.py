"""Checks on the rows of one Koinly wallet."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from .currencies import looks_like_fiat, notation_problem
from .model import Issue, Row, format_amount
from .tags import tag_problem


def in_time_order(rows: list[Row]) -> list[Row]:
    """Rows sorted by time; rows with the same time keep their original order."""
    return sorted(rows, key=lambda row: row.time)


def balance_changes(row: Row) -> list[tuple[str, Decimal]]:
    """Amounts are gross (Koinly article 9489976), so the fee always leaves the wallet on top."""
    changes = []
    if row.received:
        changes.append((row.received.currency, row.received.amount))
    if row.sent:
        changes.append((row.sent.currency, -row.sent.amount))
    if row.fee:
        changes.append((row.fee.currency, -row.fee.amount))
    return changes


def final_balances(rows: list[Row]) -> dict[str, Decimal]:
    balances: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        for currency, change in balance_changes(row):
            balances[currency] += change
    return dict(balances)


def check_rows(rows: list[Row], wallet: str, strict: bool = True) -> list[Issue]:
    """Format, tags, unique hashes and a running balance that never goes below zero.

    With strict=False (a file that may be only part of a wallet's history) repeated hashes
    and negative balances are warnings instead of errors.
    """
    issues = []
    loose = "error" if strict else "warning"
    for index, row in enumerate(rows, start=1):
        where = f"{wallet} row {index} ({row.time:%Y-%m-%d %H:%M:%S} UTC)"
        for label, money in (("sent", row.sent), ("received", row.received), ("fee", row.fee)):
            if money and (problem := notation_problem(money.currency)):
                issues.append(Issue("error", where, f"{label} currency: {problem}"))
        if row.net_worth and not looks_like_fiat(row.net_worth.currency):
            issues.append(Issue("warning", where, "Net Worth Currency accepts fiat only (USD, EUR, GBP...)"))
        if problem := tag_problem(row.tag, row.kind):
            issues.append(Issue(problem[0], where, problem[1]))
        if row.kind == "trade" and row.sent.currency == row.received.currency:
            issues.append(Issue("error", where, "a trade must exchange two different currencies"))

    counts = Counter(row.tx_hash for row in rows if row.tx_hash)
    for tx_hash, count in counts.items():
        if count > 1:
            issues.append(Issue(loose, wallet, f"TxHash {tx_hash} appears in {count} rows"))

    balances: dict[str, Decimal] = defaultdict(Decimal)
    reported = set()
    for row in in_time_order(rows):
        for currency, change in balance_changes(row):
            balances[currency] += change
            if balances[currency] < 0 and currency not in reported:
                reported.add(currency)
                issues.append(Issue(loose, wallet, (
                    f"balance of {currency} falls to {format_amount(balances[currency])} at "
                    f"{row.time:%Y-%m-%d %H:%M:%S} UTC ({row.description or row.kind}). Koinly would "
                    "report missing purchase history: a deposit is missing or rows are in the wrong order.")))
    return issues


def check_expected_balances(rows: list[Row], expected: dict[str, Decimal], wallet: str,
                            source: str = "expected_balances", hint: str = "") -> list[Issue]:
    """Compare the final balance of the file with a balance you know (exchange page, chain)."""
    issues = []
    balances = final_balances(rows)
    for currency, want in expected.items():
        have = balances.get(currency, Decimal(0))
        if have != want:
            issues.append(Issue("error", wallet, (
                f"final balance of {currency} in the file is {format_amount(have)}, "
                f"but {source} says {format_amount(want)} (difference {format_amount(have - want)})"
                + (f". {hint}" if hint else ""))))
    return issues


def describe_balances(rows: list[Row]) -> str:
    parts = [f"{format_amount(amount)} {currency}" for currency, amount in sorted(final_balances(rows).items())]
    return ", ".join(parts) or "nothing"

