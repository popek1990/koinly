"""Quantus (QTC) on-chain history -> Koinly Universal rows.

`fetch` reads the public Quantus indexer (GraphQL) and saves a snapshot of every transfer
from or to your addresses, pinned to one block, plus the current balances. `load_rows` turns
that snapshot into rows without touching the network, so a build is repeatable.

All listed addresses form ONE Koinly wallet:
- a transfer between two of your addresses changes nothing but the network fee, which is
  written as a withdrawal tagged "cost";
- incoming transfers from an address in `sender_tags` get that tag (e.g. "airdrop");
- a batch (one extrinsic paying several of your addresses) becomes one row with the sum,
  because a transaction hash should appear once per file;
- the network fee is `transfer.fee` from the indexer, counted once per extrinsic.
The final balance must equal the on-chain balance in the snapshot; anything the snapshot
does not show (for example fees of non-transfer extrinsics) makes the build stop.
"""
from __future__ import annotations

import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from koinly_csv.checks import check_expected_balances
from koinly_csv.config import Config, WalletConfig
from koinly_csv.model import DataError, Issue, Money, Row, format_amount, short_address
from koinly_csv.timezones import parse_export_time

DEFAULT_INDEXER = "https://sqm.quantus.com/v1/graphql"
DECIMALS = 12  # 1 QTC = 10**12 planck
USER_AGENT = "koinly-custom-csv/0.1 (+https://github.com/popek1990/koinly)"
PAGE = 500
TRANSFER_FIELDS = "id from_id to_id amount fee block_height timestamp extrinsic_id"
BALANCE_HINT = ("Transfers alone do not explain the balance. Usual causes: an address missing from 'addresses', "
                "fees of extrinsics that are not transfers, or dust removed when an address was emptied below "
                "the existential deposit. Find the gap in a block explorer and add it as a withdrawal in a "
                "manual file (Koinly's 'cost' tag fits a network fee).")


def _options(wallet: WalletConfig) -> tuple[list[str], str, int]:
    addresses = [str(a).strip() for a in wallet.options.get("addresses", [])]
    if not addresses:
        raise DataError(f"{wallet.name}: 'addresses' is empty")
    if len(set(addresses)) != len(addresses):
        raise DataError(f"{wallet.name}: an address is listed twice")
    asset = str(wallet.options.get("asset", "QTC"))
    decimals = int(wallet.options.get("decimals", DECIMALS))
    return addresses, asset, decimals


# ---------------------------------------------------------------- fetch (network)

def _graphql(url: str, query: str) -> dict:
    request = urllib.request.Request(url, json.dumps({"query": query}).encode(),
                                     {"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        answer = json.load(response)
    if answer.get("errors"):
        raise DataError(f"indexer error: {answer['errors']}")
    return answer["data"]


def _count(url: str, where: str) -> int:
    data = _graphql(url, "{transfer_aggregate(where:{%s}){aggregate{count}}}" % where)
    return int(data["transfer_aggregate"]["aggregate"]["count"])


def _transfers(url: str, where: str) -> list[dict]:
    expected = _count(url, where)
    rows: list[dict] = []
    while len(rows) < expected:
        page = _graphql(url, "{transfer(where:{%s},order_by:[{block_height:asc},{id:asc}],limit:%d,offset:%d){%s}}"
                        % (where, PAGE, len(rows), TRANSFER_FIELDS))["transfer"]
        if not page:
            raise DataError(f"indexer returned {len(rows)} of {expected} transfers")
        rows += page
    if len({row["id"] for row in rows}) != expected:
        raise DataError("indexer returned duplicate or missing transfers")
    return rows


def fetch(wallet: WalletConfig, config: Config) -> str:
    addresses, _, _ = _options(wallet)
    url = str(wallet.options.get("indexer", DEFAULT_INDEXER))
    target = config.resolve(str(wallet.options["snapshot"]))
    listed = json.dumps(addresses)
    for _attempt in range(3):
        block = _graphql(url, "{block(order_by:{height:desc},limit:1){height hash timestamp}}")["block"][0]
        height = int(block["height"])
        found: dict[str, dict] = {}
        for side in ("from_id", "to_id"):
            for row in _transfers(url, "%s:{_in:%s},block_height:{_lte:%d}" % (side, listed, height)):
                found[row["id"]] = row
        accounts = _graphql(url, "{account(where:{id:{_in:%s}}){id free reserved}}" % listed)["account"]
        # Balances are read after the pinned block; retry if anything of ours moved in between.
        moved = sum(_count(url, "%s:{_in:%s},block_height:{_gt:%d}" % (side, listed, height))
                    for side in ("from_id", "to_id"))
        if moved == 0:
            break
    else:
        raise DataError("your addresses kept moving during the fetch; try again later")
    snapshot = {
        "source": url,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "block": block,
        "addresses": addresses,
        "accounts": {a["id"]: {"free": str(a["free"]), "reserved": str(a["reserved"])} for a in accounts},
        "transfers": sorted(found.values(), key=lambda row: (int(row["block_height"]), row["id"])),
    }
    _write_private_json(target, snapshot)
    return f"{wallet.name}: {len(found)} transfers up to block {height} -> {target}"


def _write_private_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, ensure_ascii=False)
        handle.write("\n")


# ---------------------------------------------------------------- rows (offline)

def load_rows(wallet: WalletConfig, config: Config) -> tuple[list[Row], list[Issue]]:
    addresses, asset, decimals = _options(wallet)
    currency = config.currency(asset)
    unit = Decimal(10) ** decimals
    path = config.resolve(str(wallet.options.get("snapshot", "")))
    if not path.is_file():
        return [], [Issue("error", wallet.name, f"snapshot {path} not found; run the fetch command first")]
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    mine = set(addresses)
    missing = mine - set(snapshot.get("addresses", []))
    if missing:
        return [], [Issue("error", wallet.name, f"snapshot does not cover {len(missing)} listed address(es); "
                                                "run the fetch command again")]
    sender_tags = {str(k): str(v) for k, v in wallet.options.get("sender_tags", {}).items()}

    groups: dict[str, list[dict]] = defaultdict(list)
    for transfer in snapshot["transfers"]:
        groups[transfer.get("extrinsic_id") or f"transfer-{transfer['id']}"].append(transfer)

    rows: list[Row] = []
    issues: list[Issue] = []
    for key, transfers in groups.items():
        tx_hash = "" if key.startswith("transfer-") else key
        when = parse_export_time(transfers[0]["timestamp"])
        incoming = [t for t in transfers if t["to_id"] in mine and t["from_id"] not in mine]
        outgoing = [t for t in transfers if t["from_id"] in mine and t["to_id"] not in mine]
        internal = [t for t in transfers if t["from_id"] in mine and t["to_id"] in mine]
        ours_paying = outgoing + internal
        fee = max((Decimal(t.get("fee") or 0) for t in ours_paying), default=Decimal(0)) / unit
        fee_money = Money(fee, currency) if fee > 0 else None
        where = f"{wallet.name} {tx_hash or key}"

        if incoming and ours_paying:
            issues.append(Issue("error", where, "one extrinsic both pays and receives; add it by hand"))
            continue

        by_tag: dict[str, list[dict]] = defaultdict(list)
        for t in incoming:
            by_tag[sender_tags.get(t["from_id"], "")].append(t)
        if len(by_tag) > 1:
            issues.append(Issue("error", where, "one extrinsic mixes senders with different tags; add it by hand"))
            continue
        for tag, items in by_tag.items():
            total = sum(Decimal(t["amount"]) for t in items) / unit
            receivers = sorted({short_address(t["to_id"]) for t in items})
            senders = sorted({short_address(t["from_id"]) for t in items})
            what = f"{tag.capitalize()}: received" if tag else "Received"
            batch = f" ({len(items)} transfers in one batch)" if len(items) > 1 else ""
            rows.append(Row(when, received=Money(total, currency), tag=tag, tx_hash=tx_hash, description=(
                f"{what} {format_amount(total)} {asset} on own {' '.join(receivers)} "
                f"from {' '.join(senders)}{batch}")))

        if outgoing:
            total = sum(Decimal(t["amount"]) for t in outgoing) / unit
            receivers = sorted({short_address(t["to_id"]) for t in outgoing})
            rows.append(Row(when, sent=Money(total, currency), fee=fee_money, tx_hash=tx_hash, description=(
                f"Sent {format_amount(total)} {asset} to {' '.join(receivers)}")))
        elif internal and fee_money:
            moved = sum(Decimal(t["amount"]) for t in internal) / unit
            pair = f"{short_address(internal[0]['from_id'])} -> {short_address(internal[0]['to_id'])}"
            rows.append(Row(when, sent=fee_money, tag="cost", tx_hash=tx_hash, description=(
                f"Network fee for moving {format_amount(moved)} {asset} between own addresses ({pair})")))

    balance = sum(Decimal(a["free"]) + Decimal(a["reserved"]) for a in snapshot.get("accounts", {}).values()) / unit
    issues += check_expected_balances(rows, {currency: balance}, wallet.name,
                                      source=f"the chain at block {snapshot['block']['height']}", hint=BALANCE_HINT)
    return rows, issues
