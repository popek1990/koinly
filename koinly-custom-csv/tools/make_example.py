#!/usr/bin/env python3
"""Generate the invented example in examples/safetrade-quantus/.

Every address, hash, amount and time is made up. A fixed seed makes the output identical on
every run, and the tests check that. Addresses and hashes are meant to look fake at a glance:
qzEXAMPLE..., 0x000...a1, 0x5000...01.

  python3 tools/make_example.py            regenerate inputs, config and expected output
  python3 tools/make_example.py --into DIR write the inputs and config somewhere else
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

EXAMPLE = HERE.parent / "examples" / "safetrade-quantus"
SEED = 7
ZONE = "Europe/Berlin"
PLANCK = Decimal(10) ** 12
USDT_CONTRACT = "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9"
USDC_CONTRACT = "0xaf88d065e77c8cc2239327c5edb3a432268e5831"
TRADE_FEE = Decimal("0.001")
QTC_DEPOSIT_FEE = Decimal("0.005")
QTC_WITHDRAWAL_FEE = Decimal("0.02")
USDT_WITHDRAWAL_FEE = Decimal("1.5")


def fake_qz(role: str, tail: str) -> str:
    return f"qzEXAMPLE{role}".ljust(44, "1") + tail


def fake_evm(number: int) -> str:
    return "0x" + f"{number:040x}"


def quantus_hash(number: int) -> str:
    return "0x5" + f"{number:063x}"


def evm_hash(number: int) -> str:
    return "0xe" + f"{number:063x}"


USER_A = fake_qz("UserWalletA", "UsrA")
USER_B = fake_qz("UserWalletB", "UsrB")
AIRDROP_PAYER = fake_qz("AirdropPayer", "Drop")
SAFETRADE_DEPOSIT = fake_qz("SafeTradeDeposit", "Depo")
SAFETRADE_HOT = fake_qz("SafeTradeHotWallet", "HotW")
EVM_MINE = fake_evm(0xA1)       # in Koinly already (synced by address)
EVM_FRIEND = fake_evm(0xB2)     # not in Koinly
EVM_EXCHANGE = fake_evm(0xC3)   # SafeTrade's hot wallet on the EVM chain


class Story:
    """Builds the exchange export, the chain snapshots and the typed-in rows together."""

    def __init__(self) -> None:
        self.rng = random.Random(SEED)
        self.trades: list[list[str]] = []
        self.transactions: list[list[str]] = []
        self.typed_in: list[dict[str, str]] = []
        self.chain: list[dict] = []
        self.receipts: dict[str, dict] = {}
        self.exchange = {"QUANTUS": Decimal(0), "USDT": Decimal(0), "USDC": Decimal(0)}
        self.onchain = {USER_A: Decimal(0), USER_B: Decimal(0)}
        self.block = 1000
        self.order = 5000
        self.trade = 70000

    # helpers -------------------------------------------------------------
    def amount(self, low: str, high: str, places: int) -> Decimal:
        step = Decimal(1).scaleb(-places)
        low_steps, high_steps = int(Decimal(low) / step), int(Decimal(high) / step)
        return Decimal(self.rng.randint(low_steps, high_steps)) * step

    def jitter(self, moment: datetime, seconds: int = 59) -> datetime:
        return moment + timedelta(seconds=self.rng.randint(0, seconds))

    @staticmethod
    def utc_text(moment: datetime) -> str:
        return moment.strftime("%Y-%m-%d %H:%M:%S")

    def chain_transfer(self, when: datetime, sender: str, receiver: str, amount: Decimal, fee: Decimal,
                       tx_hash: str, index: int = 1) -> None:
        if index == 1:
            self.block += 1
        self.chain.append({
            "id": f"{self.block:010d}-e0000-{index:06d}", "from_id": sender, "to_id": receiver,
            "amount": str(int(amount * PLANCK)), "fee": str(int(fee * PLANCK)), "block_height": self.block,
            "timestamp": when.strftime("%Y-%m-%dT%H:%M:%S.000+00:00"), "extrinsic_id": tx_hash,
        })
        if sender in self.onchain:
            self.onchain[sender] -= amount + fee
            assert self.onchain[sender] >= 0
        if receiver in self.onchain:
            self.onchain[receiver] += amount

    def evm_transfer(self, when: datetime, token: str, sender: str, receiver: str, amount: Decimal,
                     tx_hash: str) -> None:
        self.receipts[tx_hash] = {
            "status": 1, "block": 400_000_000 + len(self.receipts) * 1000,
            "time": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "token_transfers": [{"token": token, "from": sender, "to": receiver,
                                 "raw_amount": str(int(amount * 10 ** 6))}],
        }

    def exchange_move(self, when: datetime, label: str, code: str, amount: Decimal, fee: Decimal,
                      tx_hash: str) -> None:
        if label == "Deposit":
            self.exchange[code] += amount - fee
        else:
            self.exchange[code] -= amount + fee
        assert self.exchange[code] >= 0, (label, code)
        signed = amount if label == "Deposit" else -amount
        self.transactions.append([self.utc_text(when), label, code, str(signed), code, str(fee), tx_hash])

    def exchange_trade(self, when: datetime, base: str, quote: str, side: str, amount: Decimal, price: Decimal,
                       order: int | None = None) -> None:
        total = amount * price
        if side == "Buy":
            fee, fee_code = amount * TRADE_FEE, base
            self.exchange[quote] -= total
            self.exchange[base] += amount - fee
        else:
            fee, fee_code = total * TRADE_FEE, quote
            self.exchange[base] -= amount
            self.exchange[quote] += total - fee
        assert self.exchange[base] >= 0 and self.exchange[quote] >= 0
        if order is None:
            self.order += 1
            order = self.order
        self.trade += 1
        self.trades.append([self.utc_text(when), f"{base}-{quote}", side, str(amount), str(total), str(fee),
                            fee_code, str(order), str(self.trade)])

    # the story -----------------------------------------------------------
    def run(self) -> None:
        day = datetime(2026, 3, 26, tzinfo=timezone.utc)

        # 1. An airdrop paid in one batch to both of your addresses.
        airdrop_a = self.amount("40", "60", 12)
        airdrop_b = self.amount("10", "20", 12)
        when = self.jitter(day + timedelta(hours=10, minutes=4))
        self.chain_transfer(when, AIRDROP_PAYER, USER_A, airdrop_a, Decimal("0.0021"), quantus_hash(1), 1)
        self.chain_transfer(when, AIRDROP_PAYER, USER_B, airdrop_b, Decimal("0.0021"), quantus_hash(1), 2)

        # 2. Move QTC from address A to SafeTrade.
        deposit = self.amount("35", "39", 3)
        sent_at = self.jitter(day + timedelta(hours=13, minutes=51))
        self.chain_transfer(sent_at, USER_A, SAFETRADE_DEPOSIT, deposit, self.amount("0.0009", "0.0015", 12),
                            quantus_hash(2))
        credited_at = sent_at + timedelta(minutes=self.rng.randint(3, 6), seconds=self.rng.randint(0, 59))
        self.exchange_move(credited_at, "Deposit", "QUANTUS", deposit, QTC_DEPOSIT_FEE, quantus_hash(2))

        # 3. Sell most of it for USDT; the first order fills in two parts.
        to_sell = (self.exchange["QUANTUS"] - Decimal("0.3")).quantize(Decimal("0.001"), ROUND_DOWN)
        steps = int(to_sell * 1000)
        cuts = sorted(Decimal(n) / 1000 for n in self.rng.sample(range(2000, steps - 2000), 3))
        pieces = [b - a for a, b in zip([Decimal(0)] + cuts, cuts + [to_sell])]
        moment = credited_at
        for number, piece in enumerate(pieces):
            moment = self.jitter(moment + timedelta(minutes=self.rng.randint(8, 50)))
            price = self.amount("20", "24", 3)
            if number == 0:
                self.order += 1
                first = (piece / 2).quantize(Decimal("0.001"), ROUND_DOWN)
                self.exchange_trade(moment, "QUANTUS", "USDT", "Sell", first, price, self.order)
                self.exchange_trade(moment, "QUANTUS", "USDT", "Sell", piece - first, price, self.order)
            else:
                self.exchange_trade(moment, "QUANTUS", "USDT", "Sell", piece, price)

        # 4. Deposit USDC from your EVM wallet and convert it to USDT.
        onchain_at = self.jitter(day + timedelta(days=1, hours=9, minutes=10))
        self.evm_transfer(onchain_at, USDC_CONTRACT, EVM_MINE, EVM_EXCHANGE, Decimal("150"), evm_hash(1))
        self.exchange_move(onchain_at + timedelta(seconds=100), "Deposit", "USDC", Decimal("150"), Decimal(0),
                           evm_hash(1))
        self.exchange_trade(onchain_at + timedelta(minutes=6), "USDC", "USDT", "Sell", Decimal("150"),
                            Decimal("0.9995"))

        # 5. Withdraw USDT the night clocks go forward in Europe (29 March, 01:00 UTC).
        requested = self.jitter(day + timedelta(days=3, minutes=48))
        self.exchange_move(requested, "Withdrawal", "USDT", Decimal("500"), USDT_WITHDRAWAL_FEE, evm_hash(2))
        arrived = requested + timedelta(minutes=15, seconds=self.rng.randint(0, 59))
        self.evm_transfer(arrived, USDT_CONTRACT, EVM_EXCHANGE, EVM_MINE, Decimal("500"), evm_hash(2))
        # The same withdrawal typed in from the web panel (local time); the build skips it as a duplicate.
        self.typed(requested, Decimal("500"), evm_hash(2), "Typed in from the SafeTrade panel")

        # 6. Buy some QTC back and withdraw it to address B.
        bought_at = self.jitter(day + timedelta(days=4, hours=10, minutes=20))
        self.exchange_trade(bought_at, "QUANTUS", "USDT", "Buy", Decimal("10"), self.amount("20", "22", 3))
        requested = self.jitter(bought_at + timedelta(minutes=40))
        self.exchange_move(requested, "Withdrawal", "QUANTUS", Decimal("9.9"), QTC_WITHDRAWAL_FEE, quantus_hash(3))
        self.chain_transfer(requested + timedelta(seconds=90), SAFETRADE_HOT, USER_B, Decimal("9.9"),
                            Decimal("0.0011"), quantus_hash(3))

        # 7. Move QTC between your own addresses: only the network fee changes the wallet.
        self.chain_transfer(self.jitter(day + timedelta(days=5, hours=8, minutes=12)), USER_B, USER_A,
                            Decimal("5.25"), self.amount("0.0009", "0.0015", 12), quantus_hash(4))

        # 8. Withdraw USDT to a wallet that is NOT in Koinly (a broken transfer).
        requested = self.jitter(day + timedelta(days=6, hours=16, minutes=20))
        self.exchange_move(requested, "Withdrawal", "USDT", Decimal("120"), USDT_WITHDRAWAL_FEE, evm_hash(3))
        self.evm_transfer(requested + timedelta(minutes=4), USDT_CONTRACT, EVM_EXCHANGE, EVM_FRIEND,
                          Decimal("120"), evm_hash(3))

        # 9. A withdrawal the export does not have yet, typed in from the web panel in local time.
        requested = self.jitter(day + timedelta(days=7, hours=8, minutes=15))
        amount = (self.exchange["USDT"] - USDT_WITHDRAWAL_FEE - self.amount("3", "8", 2)).quantize(Decimal("0.01"))
        self.exchange["USDT"] -= amount + USDT_WITHDRAWAL_FEE
        self.typed(requested, amount, evm_hash(4), "Typed in from the SafeTrade panel; not in the export yet")
        self.evm_transfer(requested + timedelta(minutes=4), USDT_CONTRACT, EVM_EXCHANGE, EVM_MINE, amount, evm_hash(4))

    def typed(self, when: datetime, amount: Decimal, tx_hash: str, note: str) -> None:
        from koinly_csv.timezones import format_local, get_zone
        self.typed_in.append({
            "Date": format_local(when, get_zone(ZONE)), "Sent Amount": str(amount), "Sent Currency": "USDT",
            "Received Amount": "", "Received Currency": "", "Fee Amount": str(USDT_WITHDRAWAL_FEE),
            "Fee Currency": "USDT", "Tag": "", "Description": note, "TxHash": tx_hash,
        })


CONFIG = """\
# Example config for the invented SafeTrade + Quantus history in this folder.
# Every address, hash and amount here is made up. Copy this file to private/config.toml
# and replace the values with your own; private/ is ignored by git.

# Zone the output files are written in. Pick the same zone in Koinly's import dialog.
timezone = "{zone}"
output_dir = "output"
# Also write a UTC copy in output/utc/ (import it with "Auto-detect / UTC").
utc_copy = true

# How each asset is written for Koinly. ID: numbers come from Koinly's Markets page;
# SYMBOL:CONTRACT picks the exact token (here: Arbitrum One USDT and USDC).
[assets]
QTC = "ID:56784085"
USDT = "USDT:{usdt}"
USDC = "USDC:{usdc}"

[[wallets]]
name = "Quantus wallet"
adapter = "quantus"
output = "quantus.csv"
asset = "QTC"
snapshot = "input/quantus-snapshot.json"
addresses = [
  "{user_a}",
  "{user_b}",
]

# Incoming transfers from these senders get a Koinly tag.
[wallets.sender_tags]
"{payer}" = "airdrop"

[[wallets]]
name = "SafeTrade"
adapter = "safetrade"
output = "safetrade.csv"
exports = ["input/safetrade/*.csv"]
# Rows you typed in yourself (Universal columns), with the zone they are written in.
manual_files = [{{ path = "input/manual/safetrade-typed-in.csv", timezone = "{zone}" }}]

# SafeTrade currency code -> asset key above. On SafeTrade, QTC is Qubitcoin.
[wallets.symbols]
QUANTUS = "QTC"
USDT = "USDT"
USDC = "USDC"

# What the exchange shows as your balance now. The build stops if the file disagrees.
[wallets.expected_balances]
QTC = "{qtc_left}"
USDT = "{usdt_left}"
USDC = "0"

# Check USDT/USDC deposits and withdrawals against the EVM chain.
[evm]
rpc = "https://arb1.arbitrum.io/rpc"
snapshot = "input/evm-snapshot.json"
# Your EVM addresses that Koinly already knows (synced by address or API).
koinly_wallets = ["{evm_mine}"]

[evm.tokens]
"{usdt}" = {{ asset = "USDT", decimals = 6 }}
"{usdc}" = {{ asset = "USDC", decimals = 6 }}
"""


def _write_csv(path: Path, header: list[str], rows: list[list[str]], terminator: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator=terminator)
        writer.writerow(header)
        writer.writerows(rows)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def generate(target: Path) -> None:
    story = Story()
    story.run()
    _write_csv(target / "input/safetrade/snapshot-trades-1775100000.csv",
               ["Koinly Date", "Pair", "Side", "Amount", "Total", "Fee Amount", "Fee Currency", "Order ID", "Trade ID"],
               story.trades)
    _write_csv(target / "input/safetrade/snapshot-transactions-1775100060.csv",
               ["Koinly Date", "Label", "Currency", "Amount", "Fee Currency", "Fee", "TxHash"],
               story.transactions)
    typed_header = list(story.typed_in[0])
    _write_csv(target / "input/manual/safetrade-typed-in.csv", typed_header,
               [[row[key] for key in typed_header] for row in story.typed_in], "\r\n")
    _write_json(target / "input/quantus-snapshot.json", {
        "source": "https://sqm.quantus.com/v1/graphql",
        "fetched_at": "2026-04-02T12:00:00Z",
        "block": {"height": story.block + 5, "hash": "0x" + "b" * 64, "timestamp": "2026-04-02T12:00:00.000+00:00"},
        "addresses": [USER_A, USER_B],
        "accounts": {address: {"free": str(int(balance * PLANCK)), "reserved": "0"}
                     for address, balance in story.onchain.items()},
        "transfers": [t for t in story.chain if t["from_id"] in story.onchain or t["to_id"] in story.onchain],
    })
    _write_json(target / "input/evm-snapshot.json", {
        "rpc": "https://arb1.arbitrum.io/rpc", "fetched_at": "2026-04-02T12:00:00Z", "receipts": story.receipts,
    })
    (target / "config.toml").write_text(CONFIG.format(
        zone=ZONE, usdt=USDT_CONTRACT, usdc=USDC_CONTRACT, user_a=USER_A, user_b=USER_B, payer=AIRDROP_PAYER,
        qtc_left=story.exchange["QUANTUS"].normalize(), usdt_left=story.exchange["USDT"].normalize(),
        evm_mine=EVM_MINE), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--into", type=Path, help="write inputs and config here instead of the example folder")
    args = parser.parse_args()
    target = args.into or EXAMPLE
    generate(target)
    if args.into:
        print(f"example inputs written to {target}")
        return 0
    from koinly_csv import build, config
    result = build.build(config.load(target / "config.toml"), target / "expected")
    for line in result.summary:
        print(line)
    for issue in result.issues:
        print(issue)
    return 1 if any(issue.level == "error" for issue in result.issues) else 0


if __name__ == "__main__":
    sys.exit(main())
