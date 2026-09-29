"""Check exchange deposits and withdrawals of ERC-20 tokens against an EVM chain.

Many people keep their EVM wallet in Koinly through an API or address sync, and only the
exchange comes from a CSV. For Koinly to merge an exchange withdrawal with the deposit it
sees on chain, the CSV must use the same token (contract notation) and the exchange time
must not be later than the block time (see koinly_csv/transfers.py).

`fetch` saves, for every hash of a row whose currency maps to a token in [evm.tokens],
the receipt's token transfers and the block time. `chain_legs` turns that snapshot into
the on-chain side of each transfer, so the build can predict Koinly's matching.
Works with any EVM JSON-RPC endpoint; the example uses Arbitrum One.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from koinly_csv.config import Config
from koinly_csv.model import DataError, Issue, Row, format_amount, short_address
from koinly_csv.timezones import parse_export_time
from koinly_csv.transfers import Leg

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
USER_AGENT = "koinly-custom-csv/0.1 (+https://github.com/popek1990/koinly)"


def _settings(config: Config) -> tuple[str, Path, dict[str, tuple[str, int]], set[str]]:
    evm = config.evm or {}
    tokens = {}
    for contract, spec in evm.get("tokens", {}).items():
        asset = str(spec["asset"])
        tokens[str(contract).lower()] = (config.currency(asset), int(spec.get("decimals", 18)))
    koinly_wallets = {str(a).lower() for a in evm.get("koinly_wallets", [])}
    return str(evm.get("rpc", "")), config.resolve(str(evm.get("snapshot", "evm-snapshot.json"))), tokens, koinly_wallets


def _rpc(url: str, method: str, params: list) -> object:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(url, body, {"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        answer = json.load(response)
    if "error" in answer:
        raise DataError(f"RPC {method}: {answer['error']}")
    return answer["result"]


def hashes_to_check(rows_by_wallet: dict[str, list[Row]], config: Config) -> list[str]:
    _, _, tokens, _ = _settings(config)
    currencies = {currency for currency, _ in tokens.values()}
    found = set()
    for rows in rows_by_wallet.values():
        for row in rows:
            money = row.sent or row.received
            if row.kind != "trade" and row.tx_hash.startswith("0x") and money.currency in currencies:
                found.add(row.tx_hash.lower())
    return sorted(found)


def fetch(rows_by_wallet: dict[str, list[Row]], config: Config) -> str:
    url, target, tokens, _ = _settings(config)
    if not url:
        raise DataError("[evm] needs 'rpc'")
    receipts = {}
    for tx_hash in hashes_to_check(rows_by_wallet, config):
        receipt = _rpc(url, "eth_getTransactionReceipt", [tx_hash])
        if receipt is None:
            receipts[tx_hash] = None
            continue
        block = _rpc(url, "eth_getBlockByNumber", [receipt["blockNumber"], False])
        moves = []
        for log in receipt["logs"]:
            contract = log["address"].lower()
            if contract in tokens and log["topics"] and log["topics"][0] == TRANSFER_TOPIC and len(log["topics"]) == 3:
                moves.append({"token": contract, "from": "0x" + log["topics"][1][-40:],
                              "to": "0x" + log["topics"][2][-40:], "raw_amount": str(int(log["data"], 16))})
        receipts[tx_hash] = {
            "status": int(receipt["status"], 16),
            "block": int(receipt["blockNumber"], 16),
            "time": datetime.fromtimestamp(int(block["timestamp"], 16), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "token_transfers": moves,
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as handle:
        json.dump({"rpc": url, "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "receipts": receipts}, handle, indent=1)
        handle.write("\n")
    return f"EVM: {len(receipts)} transactions -> {target}"


def chain_legs(rows_by_wallet: dict[str, list[Row]], config: Config) -> tuple[list[Leg], list[Issue]]:
    """On-chain counterparts of exchange rows, for the wallets listed in [evm] koinly_wallets."""
    _, path, tokens, koinly_wallets = _settings(config)
    if not path.is_file():
        return [], [Issue("error", "evm", f"snapshot {path} not found; run the fetch command first")]
    receipts = json.loads(path.read_text(encoding="utf-8"))["receipts"]
    legs: list[Leg] = []
    issues: list[Issue] = []
    wanted = set(hashes_to_check(rows_by_wallet, config))
    for wallet, rows in rows_by_wallet.items():
        for row in rows:
            if row.tx_hash.lower() not in wanted:
                continue
            where = f"{wallet} {row.tx_hash}"
            receipt = receipts.get(row.tx_hash.lower(), "missing")
            if receipt == "missing":
                issues.append(Issue("error", where, "not in the EVM snapshot; run the fetch command again"))
                continue
            if receipt is None:
                issues.append(Issue("error", where, "transaction not found on chain (wrong chain or hash?)"))
                continue
            if receipt["status"] != 1:
                issues.append(Issue("error", where, "the on-chain transaction failed"))
                continue
            money = row.sent or row.received
            moves = []
            for move in receipt["token_transfers"]:
                currency, decimals = tokens.get(move["token"], ("", 0))
                amount = Decimal(move["raw_amount"]) / Decimal(10) ** decimals
                if currency == money.currency and amount == money.amount:
                    moves.append(move)
            if len(moves) != 1:
                issues.append(Issue("error", where, f"expected one {format_amount(money.amount)} {money.currency} "
                                                    f"token transfer on chain, found {len(moves)}"))
                continue
            move = moves[0]
            chain_time = parse_export_time(receipt["time"])
            counterpart = move["to"] if row.sent else move["from"]
            label = f"on chain, block {receipt['block']}"
            if counterpart.lower() not in koinly_wallets:
                issues.append(Issue("warning", where, (
                    f"{'destination' if row.sent else 'source'} {short_address(counterpart)} is not in "
                    "[evm] koinly_wallets; unless that wallet is in Koinly, this is a broken transfer "
                    "(Koinly treats a lone withdrawal as a sale and a lone deposit as a purchase at market price)")))
                continue
            legs.append(Leg(f"EVM {short_address(counterpart)}", "in" if row.sent else "out", chain_time,
                            money.amount, money.currency, row.tx_hash, label))
    return legs, issues
