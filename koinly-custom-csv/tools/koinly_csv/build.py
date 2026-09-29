"""Turn a config into checked Koinly files: load rows, check them, predict transfers, write."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import timezone
from pathlib import Path

from . import universal
from .checks import check_expected_balances, check_rows, describe_balances, in_time_order
from .config import Config, WalletConfig
from .model import DataError, Issue, Money, Row, has_errors
from .timezones import get_zone, zone_name
from .transfers import Leg, legs_from_rows, match, near_misses


@dataclass
class BuildResult:
    rows: dict[str, list[Row]] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    written: list[Path] = field(default_factory=list)


def _adapter(name: str):
    if name == "safetrade":
        from adapters import safetrade
        return safetrade
    if name == "quantus":
        from adapters import quantus
        return quantus
    return None  # "universal": rows come from manual_files only


def _map_currency(money: Money | None, config: Config) -> Money | None:
    if money and money.currency in config.assets:
        return Money(money.amount, config.assets[money.currency])
    return money


def _manual_rows(wallet: WalletConfig, config: Config, existing: list[Row]) -> tuple[list[Row], list[Issue]]:
    rows, issues = [], []
    hashes = {row.tx_hash for row in existing if row.tx_hash}
    for manual in wallet.manual_files:
        path = config.resolve(manual.path)
        if not path.is_file():
            issues.append(Issue("error", wallet.name, f"manual file {path} not found"))
            continue
        read_rows, read_issues = universal.read(path, get_zone(manual.timezone))
        issues += read_issues
        for row in read_rows:
            row = replace(row, sent=_map_currency(row.sent, config), received=_map_currency(row.received, config),
                          fee=_map_currency(row.fee, config))
            same = [old for old in existing if old.time == row.time and old.sent == row.sent
                    and old.received == row.received]
            if (row.tx_hash and row.tx_hash in hashes) or same:
                issues.append(Issue("note", f"{path.name}", f"row at {row.time:%Y-%m-%d %H:%M:%S} UTC is already "
                                                            "in the export; the manual copy is skipped"))
                continue
            rows.append(row)
    return rows, issues


def load_all(config: Config) -> BuildResult:
    result = BuildResult()
    for wallet in config.wallets:
        adapter = _adapter(wallet.adapter)
        try:
            rows, issues = adapter.load_rows(wallet, config) if adapter else ([], [])
            extra, extra_issues = _manual_rows(wallet, config, rows)
        except DataError as error:
            result.issues.append(Issue("error", wallet.name, str(error)))
            continue
        rows = in_time_order(rows + extra)
        result.rows[wallet.name] = rows
        result.issues += issues + extra_issues
        result.issues += check_rows(rows, wallet.name, strict=True)
        expected = {config.currency(asset): amount for asset, amount in wallet.expected_balances.items()}
        result.issues += check_expected_balances(rows, expected, wallet.name)
    return result


def transfer_report(legs: list[Leg]) -> tuple[list[str], list[Issue]]:
    outcome = match(legs)
    lines = [f"Transfers Koinly should merge: {len(outcome.pairs)}"]
    lines += [f"  {out}  >>  {inc}" for out, inc in outcome.pairs]
    issues: list[Issue] = []
    reported: set[frozenset] = set()
    for leg in outcome.unmatched:
        misses = [(other, why) for other, why in near_misses(leg, legs) if frozenset((leg, other)) not in reported]
        if not misses and not any(leg in pair for pair in reported):
            issues.append(Issue("note", leg.wallet, f"no counterpart in these files for {leg}"))
        for other, reasons in misses:
            reported.add(frozenset((leg, other)))
            issues.append(Issue("warning", leg.wallet, f"{leg} will NOT merge with {other}: {'; '.join(reasons)}"))
    return lines, issues


def build(config: Config, output_dir: Path | None = None) -> BuildResult:
    result = load_all(config)
    legs = [leg for name, rows in result.rows.items() for leg in legs_from_rows(name, rows)]
    if config.evm:
        from adapters import evm
        chain, chain_issues = evm.chain_legs(result.rows, config)
        legs += chain
        result.issues += chain_issues
    lines, transfer_issues = transfer_report(legs)
    result.issues += transfer_issues

    zone = get_zone(config.timezone)
    for name, rows in result.rows.items():
        result.summary.append(f"{name}: {len(rows)} rows, final balance {describe_balances(rows)}")
    result.summary += lines
    if has_errors(result.issues):
        result.summary.append("Nothing written: fix the errors first.")
        return result

    target = output_dir or config.resolve(config.output_dir)
    outputs = [(target, zone)] + ([(target / "utc", timezone.utc)] if config.utc_copy and zone is not timezone.utc else [])
    for wallet in config.wallets:
        rows = result.rows[wallet.name]
        for folder, folder_zone in outputs:
            path = folder / wallet.output
            write_issues = universal.write(path, rows, folder_zone)
            if folder_zone is zone:
                result.issues += write_issues
            # Compare as text: a time in the hour that happens twice reads back as its first occurrence.
            back, _ = universal.read(path, folder_zone)
            if [universal.row_to_record(r, folder_zone) for r in back] != \
                    [universal.row_to_record(r, folder_zone) for r in rows]:
                result.issues.append(Issue("error", str(path), "the written file does not read back the same"))
            result.written.append(path)
    result.summary.append(f"Written in {zone_name(zone)}: " + ", ".join(str(p) for p in result.written))
    return result


def validate_files(paths: list[Path], zone_text: str) -> BuildResult:
    """Check Universal files you already have, e.g. written by hand or by another tool."""
    result = BuildResult()
    zone = get_zone(zone_text)
    legs: list[Leg] = []
    for path in paths:
        rows, issues = universal.read(path, zone)
        rows = in_time_order(rows)
        label = str(path)
        result.rows[label] = rows
        result.issues += issues + check_rows(rows, label, strict=False)
        legs += legs_from_rows(label, rows)
        result.summary.append(f"{label}: {len(rows)} rows read as {zone_name(zone)}, "
                              f"final balance {describe_balances(rows)}")
    if len(paths) > 1:
        lines, transfer_issues = transfer_report(legs)
        result.summary += lines
        result.issues += transfer_issues
    return result

