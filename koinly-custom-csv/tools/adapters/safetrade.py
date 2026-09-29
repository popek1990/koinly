"""SafeTrade exports -> Koinly Universal rows.

SafeTrade (safe.trade) exports two CSV files whose headers look like Koinly's but match no
Koinly template exactly:

  trades:        Koinly Date,Pair,Side,Amount,Total,Fee Amount,Fee Currency,Order ID,Trade ID
  transactions:  Koinly Date,Label,Currency,Amount,Fee Currency,Fee,TxHash

Facts this adapter relies on (see docs/exchanges/safetrade.md):
- dates in the export are UTC (the web panel shows local time);
- Pair is BASE-QUOTE, Amount is the base amount, Total the quote amount, both gross;
- a withdrawal has a negative Amount; its Fee is charged on top of the amount;
- a deposit's Amount is what arrived on chain; its Fee is deducted from it;
- currency codes are SafeTrade's own: QUANTUS is Quantus, while QTC there is Qubitcoin.
The file type is detected from the header, so any file name works. Rows repeated across
several exports are kept once (by Trade ID and by TxHash).
"""
from __future__ import annotations

import csv
import glob
from pathlib import Path

from koinly_csv.config import Config, WalletConfig
from koinly_csv.model import DataError, Issue, Money, Row, format_amount, parse_decimal
from koinly_csv.timezones import parse_export_time

TRADE_COLUMNS = {"Koinly Date", "Pair", "Side", "Amount", "Total", "Fee Amount", "Fee Currency", "Trade ID"}
TRANSACTION_COLUMNS = {"Koinly Date", "Label", "Currency", "Amount", "Fee Currency", "Fee", "TxHash"}


def _files(wallet: WalletConfig, config: Config) -> list[Path]:
    patterns = wallet.options.get("exports", [])
    if isinstance(patterns, str):
        patterns = [patterns]
    found = {Path(name) for pattern in patterns for name in glob.glob(str(config.resolve(pattern)))}
    return sorted(path for path in found if path.is_file())


class _Codes:
    """SafeTrade currency code -> Koinly notation, through the wallet's [symbols] table."""

    def __init__(self, wallet: WalletConfig, config: Config):
        self.symbols = {str(k).upper(): str(v) for k, v in wallet.options.get("symbols", {}).items()}
        self.config = config

    def __call__(self, code: str) -> str:
        code = code.strip().upper()
        if code not in self.symbols:
            hint = " (on SafeTrade, QTC is Qubitcoin; Quantus is QUANTUS)" if code in ("QTC", "QUANTUS") else ""
            raise DataError(f"SafeTrade currency {code!r} is not in [wallets.symbols]{hint}")
        return self.config.currency(self.symbols[code])


def _fee(amount_text: str, currency_code: str, codes: _Codes) -> Money | None:
    amount = parse_decimal(amount_text or "0")
    if amount < 0:
        raise DataError(f"negative fee {amount_text!r}")
    return Money(amount, codes(currency_code)) if amount > 0 else None


def _trade_row(record: dict[str, str], codes: _Codes) -> Row:
    base, quote = record["Pair"].strip().upper().split("-")
    side = record["Side"].strip().capitalize()
    amount, total = parse_decimal(record["Amount"]), parse_decimal(record["Total"])
    fee = _fee(record["Fee Amount"], record["Fee Currency"], codes)
    base_money, quote_money = Money(amount, codes(base)), Money(total, codes(quote))
    price = total / amount
    ids = f"order {record.get('Order ID', '').strip()}; trade {record['Trade ID'].strip()}"
    description = (f"SafeTrade {side.lower()} {format_amount(amount)} {base} at "
                   f"{format_amount(round(price, 8))} {quote}; {ids}")
    if side == "Buy":
        sent, received = quote_money, base_money
    elif side == "Sell":
        sent, received = base_money, quote_money
    else:
        raise DataError(f"unknown Side {record['Side']!r}")
    return Row(time=parse_export_time(record["Koinly Date"]), sent=sent, received=received, fee=fee,
               description=description, tx_hash=f"safetrade-trade-{record['Trade ID'].strip()}")


def _transaction_row(record: dict[str, str], codes: _Codes) -> Row:
    label = record["Label"].strip().capitalize()
    code = record["Currency"].strip().upper()
    amount = abs(parse_decimal(record["Amount"]))
    fee = _fee(record["Fee"], record["Fee Currency"], codes)
    money = Money(amount, codes(code))
    when = parse_export_time(record["Koinly Date"])
    tx_hash = record["TxHash"].strip()
    if label == "Deposit":
        note = "; the deposit fee is deducted from it" if fee else ""
        return Row(time=when, received=money, fee=fee, tx_hash=tx_hash,
                   description=f"SafeTrade deposit of {format_amount(amount)} {code}{note}")
    if label == "Withdrawal":
        note = "; the withdrawal fee is charged on top" if fee else ""
        return Row(time=when, sent=money, fee=fee, tx_hash=tx_hash,
                   description=f"SafeTrade withdrawal of {format_amount(amount)} {code}{note}")
    raise DataError(f"unknown Label {record['Label']!r}")


def load_rows(wallet: WalletConfig, config: Config) -> tuple[list[Row], list[Issue]]:
    codes = _Codes(wallet, config)
    trades: dict[str, Row] = {}
    transactions: dict[str, Row] = {}
    issues: list[Issue] = []
    files = _files(wallet, config)
    if not files:
        issues.append(Issue("error", wallet.name, "no export files match 'exports'"))
    for path in files:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            header = set(reader.fieldnames or [])
            if TRADE_COLUMNS <= header:
                kind, target, key_name = "trade", trades, "Trade ID"
            elif TRANSACTION_COLUMNS <= header:
                kind, target, key_name = "transaction", transactions, "TxHash"
            else:
                issues.append(Issue("warning", path.name, "not a SafeTrade trades or transactions export; skipped"))
                continue
            for number, record in enumerate(reader, start=2):
                where = f"{path.name}:{number}"
                try:
                    row = _trade_row(record, codes) if kind == "trade" else _transaction_row(record, codes)
                except (DataError, KeyError, ValueError, ZeroDivisionError) as error:
                    issues.append(Issue("error", where, str(error)))
                    continue
                key = record[key_name].strip() or f"{path.name}:{number}"
                if key in target:
                    if target[key] != row:
                        issues.append(Issue("error", where, f"{key_name} {key} appears again with different data"))
                    continue
                target[key] = row
                if kind == "trade" and row.fee:
                    expected_fee_currency = row.received.currency
                    if row.fee.currency != expected_fee_currency:
                        issues.append(Issue("note", where, "trade fee is not in the received currency"))
    # At the same second: deposits, then trades, then withdrawals (a stable sort keeps this order).
    deposits = [row for row in transactions.values() if row.received]
    withdrawals = [row for row in transactions.values() if row.sent]
    return deposits + list(trades.values()) + withdrawals, issues
