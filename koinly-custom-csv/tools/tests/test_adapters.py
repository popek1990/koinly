"""Tests for the SafeTrade, Quantus and EVM adapters. All data is invented."""
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from adapters import evm, quantus, safetrade
from koinly_csv import config as configuration
from koinly_csv.build import build

QTC = "ID:56784085"
USDT = "USDT:0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9"
A = "qzEXAMPLEtestA".ljust(48, "1")
B = "qzEXAMPLEtestB".ljust(48, "2")
PAYER = "qzEXAMPLEpayer".ljust(48, "3")
STRANGER = "qzEXAMPLEother".ljust(48, "4")

CONFIG = f"""
timezone = "UTC"
utc_copy = false
[assets]
QTC = "{QTC}"
USDT = "{USDT}"

[[wallets]]
name = "Chain"
adapter = "quantus"
output = "chain.csv"
snapshot = "snapshot.json"
addresses = ["{A}", "{B}"]
[wallets.sender_tags]
"{PAYER}" = "airdrop"

[[wallets]]
name = "Exchange"
adapter = "safetrade"
output = "exchange.csv"
exports = ["exports/*.csv"]
[wallets.symbols]
QUANTUS = "QTC"
USDT = "USDT"
"""

TRADES = """Koinly Date,Pair,Side,Amount,Total,Fee Amount,Fee Currency,Order ID,Trade ID
2026-02-01 10:05:00,QUANTUS-USDT,Sell,2.000,40.000000,0.040000000,USDT,11,21
2026-02-01 10:06:00,QUANTUS-USDT,Buy,1.000,19.000000,0.001000000,QUANTUS,12,22
"""

TRANSACTIONS = """Koinly Date,Label,Currency,Amount,Fee Currency,Fee,TxHash
2026-02-01 10:00:00,Deposit,QUANTUS,3,QUANTUS,0.005,0x02
2026-02-01 11:00:00,Withdrawal,USDT,-10,USDT,1,0xe1
"""


def transfer(number, sender, receiver, amount, fee="0", extrinsic="0x01", minute=0):
    return {"id": f"{number:010d}", "from_id": sender, "to_id": receiver, "amount": str(int(Decimal(amount) * 10**12)),
            "fee": str(int(Decimal(fee) * 10**12)), "block_height": number,
            "timestamp": f"2026-02-01T09:{minute:02d}:00.000+00:00", "extrinsic_id": extrinsic}


class Workspace:
    def __init__(self, transfers, balances, trades=TRADES, transactions=TRANSACTIONS, extra="", zone="UTC"):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        (root / "exports").mkdir()
        (root / "exports/trades.csv").write_text(trades)
        (root / "exports/transactions.csv").write_text(transactions)
        (root / "config.toml").write_text(CONFIG.replace('timezone = "UTC"', f'timezone = "{zone}"') + extra)
        (root / "snapshot.json").write_text(json.dumps({
            "block": {"height": 99}, "addresses": [A, B], "transfers": transfers,
            "accounts": {address: {"free": str(int(Decimal(v) * 10**12)), "reserved": "0"}
                         for address, v in balances.items()}}))
        self.config = configuration.load(root / "config.toml")
        self.root = root

    def wallet(self, name):
        return next(w for w in self.config.wallets if w.name == name)

    def close(self):
        self.folder.cleanup()


class SafeTradeTests(unittest.TestCase):
    def test_trades_and_transactions(self):
        space = Workspace([], {})
        rows, issues = safetrade.load_rows(space.wallet("Exchange"), space.config)
        space.close()
        self.assertEqual([i for i in issues if i.level == "error"], [])
        deposit, sell, buy, withdrawal = rows
        self.assertEqual((deposit.received.amount, deposit.fee.amount), (Decimal(3), Decimal("0.005")))
        self.assertEqual((sell.sent.currency, sell.received.currency, sell.fee.currency), (QTC, USDT, USDT))
        self.assertEqual((buy.sent.amount, buy.received.amount), (Decimal(19), Decimal(1)))
        self.assertEqual((withdrawal.sent.amount, withdrawal.fee.amount), (Decimal(10), Decimal(1)))
        self.assertEqual(sell.tx_hash, "safetrade-trade-21")

    def test_unknown_code_points_to_qubitcoin(self):
        space = Workspace([], {}, transactions=TRANSACTIONS.replace("QUANTUS,3,QUANTUS", "QTC,3,QTC"))
        _, issues = safetrade.load_rows(space.wallet("Exchange"), space.config)
        space.close()
        self.assertTrue(any("Qubitcoin" in issue.message for issue in issues))

    def test_duplicate_exports_are_merged(self):
        space = Workspace([], {})
        (space.root / "exports/trades-again.csv").write_text(TRADES)
        rows, issues = safetrade.load_rows(space.wallet("Exchange"), space.config)
        space.close()
        self.assertEqual(len(rows), 4)
        self.assertEqual([i for i in issues if i.level == "error"], [])


class QuantusTests(unittest.TestCase):
    def test_airdrop_batch_internal_move_and_balance(self):
        transfers = [
            transfer(1, PAYER, A, "5", fee="0.01", extrinsic="0x01"),
            transfer(2, PAYER, B, "2", fee="0.01", extrinsic="0x01"),
            transfer(3, A, B, "1", fee="0.001", extrinsic="0x03", minute=5),
            transfer(4, B, STRANGER, "0.5", fee="0.002", extrinsic="0x04", minute=9),
        ]
        space = Workspace(transfers, {A: "3.999", B: "2.498"})
        rows, issues = quantus.load_rows(space.wallet("Chain"), space.config)
        space.close()
        self.assertEqual(issues, [])
        airdrop, fee_row, sent = rows
        self.assertEqual((airdrop.tag, airdrop.received.amount), ("airdrop", Decimal(7)))
        self.assertEqual((fee_row.tag, fee_row.sent.amount), ("cost", Decimal("0.001")))
        self.assertEqual((sent.sent.amount, sent.fee.amount), (Decimal("0.5"), Decimal("0.002")))

    def test_balance_mismatch_stops_the_build(self):
        space = Workspace([transfer(1, PAYER, A, "5")], {A: "4"})
        _, issues = quantus.load_rows(space.wallet("Chain"), space.config)
        space.close()
        self.assertEqual(issues[0].level, "error")
        self.assertIn("the chain at block 99", issues[0].message)


class BuildTests(unittest.TestCase):
    def test_transfer_between_chain_and_exchange_is_predicted(self):
        transfers = [transfer(1, PAYER, A, "5"), transfer(2, A, STRANGER, "3", fee="0.001", extrinsic="0x02", minute=58)]
        space = Workspace(transfers, {A: "1.999"})
        with tempfile.TemporaryDirectory() as out:
            result = build(space.config, Path(out))
            written = sorted(p.name for p in Path(out).iterdir())
        space.close()
        self.assertEqual([i for i in result.issues if i.level == "error"], [])
        self.assertIn("Transfers Koinly should merge: 1", result.summary)
        self.assertEqual(written, ["chain.csv", "exchange.csv"])

    def test_hour_that_happens_twice_warns_but_builds(self):
        # 00:30 and 01:30 UTC on 25 Oct 2026 are both 01:30 in London (clocks go back at 01:00 UTC).
        transactions = ("Koinly Date,Label,Currency,Amount,Fee Currency,Fee,TxHash\n"
                        "2026-10-25 00:30:00,Deposit,USDT,5,USDT,0,0xd1\n"
                        "2026-10-25 01:30:00,Deposit,USDT,6,USDT,0,0xd2\n")
        space = Workspace([], {}, trades=TRADES.splitlines()[0] + "\n", transactions=transactions, zone="Europe/London")
        with tempfile.TemporaryDirectory() as out:
            result = build(space.config, Path(out))
            local = (Path(out) / "exchange.csv").read_text()
        space.close()
        self.assertEqual([i for i in result.issues if i.level == "error"], [])
        self.assertEqual(sum("happens twice" in i.message for i in result.issues), 2)
        self.assertEqual(local.count("2026-10-25 01:30:00"), 2)

    def test_errors_mean_nothing_is_written(self):
        space = Workspace([transfer(1, PAYER, A, "5")], {A: "1"})
        with tempfile.TemporaryDirectory() as out:
            result = build(space.config, Path(out))
            self.assertEqual(list(Path(out).iterdir()), [])
        space.close()
        self.assertIn("Nothing written: fix the errors first.", result.summary)


class EvmTests(unittest.TestCase):
    EXTRA = f"""
[evm]
snapshot = "evm.json"
koinly_wallets = ["0x00000000000000000000000000000000000000a1"]
[evm.tokens]
"0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9" = {{ asset = "USDT", decimals = 6 }}
"""

    def receipts(self, space, time, to="0x00000000000000000000000000000000000000a1", raw="10000000"):
        (space.root / "evm.json").write_text(json.dumps({"receipts": {"0xe1": {
            "status": 1, "block": 7, "time": time, "token_transfers": [{
                "token": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
                "from": "0x00000000000000000000000000000000000000c3", "to": to, "raw_amount": raw}]}}}))

    def rows(self, space):
        return {"Exchange": safetrade.load_rows(space.wallet("Exchange"), space.config)[0]}

    def test_chain_leg_for_a_wallet_in_koinly(self):
        space = Workspace([], {}, extra=self.EXTRA)
        self.receipts(space, "2026-02-01T11:03:00Z")
        legs, issues = evm.chain_legs(self.rows(space), space.config)
        space.close()
        self.assertEqual(issues, [])
        self.assertEqual((legs[0].direction, legs[0].amount, legs[0].currency), ("in", Decimal(10), USDT))

    def test_wallet_outside_koinly_and_wrong_amount(self):
        space = Workspace([], {}, extra=self.EXTRA)
        self.receipts(space, "2026-02-01T11:03:00Z", to="0x00000000000000000000000000000000000000b2")
        _, issues = evm.chain_legs(self.rows(space), space.config)
        self.assertIn("broken transfer", issues[0].message)
        self.receipts(space, "2026-02-01T11:03:00Z", raw="9000000")
        _, issues = evm.chain_legs(self.rows(space), space.config)
        space.close()
        self.assertIn("found 0", issues[0].message)


class ConfigTemplateTests(unittest.TestCase):
    def test_config_example_loads(self):
        loaded = configuration.load(Path(__file__).resolve().parents[1] / "config.example.toml")
        self.assertEqual([w.adapter for w in loaded.wallets], ["quantus", "safetrade"])
        self.assertEqual(loaded.currency("QTC"), QTC)


if __name__ == "__main__":
    unittest.main()
