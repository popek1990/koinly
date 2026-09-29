"""Read and write files in Koinly's Universal template.

Column names follow Koinly help article 9489976 (checked 2026-09-29). The five required
columns must match exactly; "Koinly Date" belongs to the Simple and Trades templates only.
"""
from __future__ import annotations

import csv
import os
from datetime import tzinfo
from pathlib import Path

from .model import DataError, Issue, Money, Row, format_amount, parse_amount
from .timezones import DATE_FORMAT, local_time_problem, parse_local, zone_name

REQUIRED = ["Date", "Sent Amount", "Sent Currency", "Received Amount", "Received Currency"]
OPTIONAL = ["Fee Amount", "Fee Currency", "Net Worth Amount", "Net Worth Currency",
            "Tag", "Description", "TxHash"]
# Also documented by Koinly, but not produced by these tools.
OTHER_KNOWN = ["Fee Worth"]


def columns_for(rows: list[Row]) -> list[str]:
    columns = REQUIRED + ["Fee Amount", "Fee Currency"]
    if any(row.net_worth for row in rows):
        columns += ["Net Worth Amount", "Net Worth Currency"]
    return columns + ["Tag", "Description", "TxHash"]


def _cells(money: Money | None) -> tuple[str, str]:
    return (format_amount(money.amount), money.currency) if money else ("", "")


def row_to_record(row: Row, zone: tzinfo) -> dict[str, str]:
    sent, received, fee, worth = (_cells(m) for m in (row.sent, row.received, row.fee, row.net_worth))
    return {
        "Date": row.time.astimezone(zone).strftime(DATE_FORMAT),
        "Sent Amount": sent[0], "Sent Currency": sent[1],
        "Received Amount": received[0], "Received Currency": received[1],
        "Fee Amount": fee[0], "Fee Currency": fee[1],
        "Net Worth Amount": worth[0], "Net Worth Currency": worth[1],
        "Tag": row.tag, "Description": row.description, "TxHash": row.tx_hash,
    }


def write(path: Path, rows: list[Row], zone: tzinfo) -> list[Issue]:
    """Write rows as they are ordered. The file is created readable by its owner only."""
    issues = []
    columns = columns_for(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
        writer.writeheader()
        for number, row in enumerate(rows, start=2):
            local = row.time.astimezone(zone)
            if local_time_problem(local.replace(tzinfo=None), zone) == "ambiguous":
                issues.append(Issue("warning", f"{path.name}:{number}",
                                    f"{local:%Y-%m-%d %H:%M:%S} happens twice in {zone_name(zone)} "
                                    "(clocks went back); Koinly may place this row an hour off. "
                                    "Use a UTC file if this row is part of a transfer."))
            writer.writerow(row_to_record(row, zone))
    return issues


def _money(record: dict[str, str], amount_key: str, currency_key: str) -> Money | None:
    amount, currency = record.get(amount_key, "").strip(), record.get(currency_key, "").strip()
    if not amount and not currency:
        return None
    if not amount or not currency:
        raise DataError(f"{amount_key!r} and {currency_key!r} must be filled together")
    return Money(parse_amount(amount), currency)


def header_issues(fieldnames: list[str] | None, where: str) -> list[Issue]:
    if not fieldnames:
        return [Issue("error", where, "the file is empty")]
    issues = []
    if len(set(fieldnames)) != len(fieldnames):
        issues.append(Issue("error", where, "a column name appears twice"))
    missing = [name for name in REQUIRED if name not in fieldnames]
    if missing:
        hint = ' ("Koinly Date" is for the Simple and Trades templates; Universal uses "Date")' \
            if "Koinly Date" in fieldnames else ""
        issues.append(Issue("error", where, f"missing required columns {missing}{hint}"))
    known = set(REQUIRED + OPTIONAL + OTHER_KNOWN)
    unknown = [name for name in fieldnames if name not in known]
    if unknown:
        issues.append(Issue("warning", where, f"columns not in the Universal template: {unknown}"))
    return issues


def read(path: Path, zone: tzinfo) -> tuple[list[Row], list[Issue]]:
    """Read a Universal file written in `zone`. Rows with errors are reported and skipped."""
    rows, issues = [], []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        issues += header_issues(reader.fieldnames, path.name)
        if any(issue.level == "error" for issue in issues):
            return rows, issues
        for number, record in enumerate(reader, start=2):
            where = f"{path.name}:{number}"
            if None in record:
                issues.append(Issue("error", where, "more cells than columns"))
                continue
            try:
                when = parse_local(record["Date"], zone)
                naive = when.astimezone(zone).replace(tzinfo=None)
                if local_time_problem(naive, zone) == "ambiguous":
                    issues.append(Issue("warning", where, f"{record['Date']} happens twice in "
                                        f"{zone_name(zone)}; Koinly may place this row an hour off"))
                rows.append(Row(
                    time=when,
                    sent=_money(record, "Sent Amount", "Sent Currency"),
                    received=_money(record, "Received Amount", "Received Currency"),
                    fee=_money(record, "Fee Amount", "Fee Currency"),
                    net_worth=_money(record, "Net Worth Amount", "Net Worth Currency"),
                    tag=(record.get("Tag") or "").strip(),
                    description=record.get("Description") or "",
                    tx_hash=(record.get("TxHash") or "").strip(),
                ))
            except DataError as error:
                issues.append(Issue("error", where, str(error)))
    return rows, issues
