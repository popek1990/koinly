"""Tests for the shared building blocks. All data is invented."""
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from koinly_csv import universal
from koinly_csv.checks import check_expected_balances, check_rows, final_balances
from koinly_csv.currencies import notation_problem
from koinly_csv.model import DataError, Money, Row, format_amount, parse_amount
from koinly_csv.tags import tag_problem
from koinly_csv.timezones import get_zone, local_time_problem, parse_local

UTC = timezone.utc
T = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)


def m(amount, currency="BTC"):
    return Money(Decimal(amount), currency)


class AmountTests(unittest.TestCase):
    def test_format_has_no_exponent_or_trailing_zeros(self):
        self.assertEqual(format_amount(Decimal("100")), "100")
        self.assertEqual(format_amount(Decimal("0.000000100")), "0.0000001")
        self.assertEqual(format_amount(Decimal("1E+3")), "1000")

    def test_strict_parser_rejects_signs_commas_and_exponents(self):
        self.assertEqual(parse_amount("12.50"), Decimal("12.5"))
        for bad in ("-1", "1,5", "1e3", "", " . "):
            with self.assertRaises(DataError):
                parse_amount(bad)

    def test_money_must_be_positive(self):
        with self.assertRaises(DataError):
            m("0")


class CurrencyTests(unittest.TestCase):
    def test_valid_notations(self):
        for text in ("BTC", "ID:18431515", "USDT:0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
                     "WIF:EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm:SOL"):
            self.assertIsNone(notation_problem(text), text)

    def test_invalid_notations(self):
        for text in ("", " BTC", "ID:abc", "USDT:", "USD T"):
            self.assertIsNotNone(notation_problem(text), text)


class TagTests(unittest.TestCase):
    def test_direction(self):
        self.assertIsNone(tag_problem("airdrop", "deposit"))
        self.assertEqual(tag_problem("airdrop", "withdrawal")[0], "error")
        self.assertIsNone(tag_problem("cost", "withdrawal"))
        self.assertEqual(tag_problem("swap", "trade")[0], "warning")
        self.assertEqual(tag_problem("Airdrop", "deposit")[0], "warning")
        self.assertEqual(tag_problem("mined", "deposit")[0], "error")


class TimezoneTests(unittest.TestCase):
    def test_daylight_saving_edges(self):
        london = get_zone("Europe/London")
        self.assertEqual(local_time_problem(datetime(2026, 10, 25, 1, 30), london), "ambiguous")
        self.assertEqual(local_time_problem(datetime(2026, 3, 29, 1, 30), london), "nonexistent")
        self.assertIsNone(local_time_problem(datetime(2026, 7, 1, 1, 30), london))

    def test_parse_local_converts_to_utc(self):
        london = get_zone("Europe/London")
        self.assertEqual(parse_local("2026-07-01 13:00:00", london), datetime(2026, 7, 1, 12, 0, tzinfo=UTC))
        self.assertEqual(parse_local("2026-01-01 13:00", london), datetime(2026, 1, 1, 13, 0, tzinfo=UTC))
        with self.assertRaises(DataError):
            parse_local("2026-03-29 01:30:00", london)
        with self.assertRaises(DataError):
            parse_local("01/07/2026 13:00", london)


class UniversalFileTests(unittest.TestCase):
    def test_round_trip_in_a_local_zone(self):
        zone = get_zone("America/New_York")
        rows = [
            Row(T, received=m("1.5"), tag="airdrop", description="gift, with a comma", tx_hash="0xabc"),
            Row(T, sent=m("0.5"), received=m("10000", "USD"), fee=m("5", "USD"), net_worth=m("10000", "USD")),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "out.csv"
            universal.write(path, rows, zone)
            text = path.read_text()
            self.assertTrue(text.startswith("Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"))
            self.assertIn("2026-01-10 07:00:00", text)
            back, issues = universal.read(path, zone)
        self.assertEqual(issues, [])
        self.assertEqual(back, rows)

    def test_header_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            path.write_text("Koinly Date,Sent Amount,Sent Currency,Received Amount,Received Currency\n")
            _, issues = universal.read(path, UTC)
        self.assertEqual(issues[0].level, "error")
        self.assertIn("Koinly Date", issues[0].message)

    def test_row_errors_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            path.write_text("Date,Sent Amount,Sent Currency,Received Amount,Received Currency\n"
                            "2026-01-10 12:00:00,1,,,\n"
                            "2026-01-10 12:00:00,,,,\n"
                            "2026-01-10 12:00:00,-1,BTC,,\n")
            rows, issues = universal.read(path, UTC)
        self.assertEqual(rows, [])
        self.assertEqual([issue.level for issue in issues], ["error"] * 3)


class CheckTests(unittest.TestCase):
    def test_negative_balance_and_repeated_hash(self):
        rows = [Row(T, sent=m("1"), tx_hash="0x1"), Row(T, received=m("2"), tx_hash="0x1")]
        messages = [issue.message for issue in check_rows(rows, "w")]
        self.assertTrue(any("appears in 2 rows" in text for text in messages))
        self.assertTrue(any("falls to -1" in text for text in messages))
        self.assertTrue(all(issue.level == "warning" for issue in check_rows(rows, "w", strict=False)))

    def test_fee_leaves_the_wallet_on_top_of_the_amount(self):
        rows = [Row(T, received=m("10"), fee=m("0.1")), Row(T, sent=m("5"), fee=m("0.2"))]
        self.assertEqual(final_balances(rows), {"BTC": Decimal("4.7")})
        self.assertEqual(check_expected_balances(rows, {"BTC": Decimal("4.7")}, "w"), [])
        self.assertEqual(len(check_expected_balances(rows, {"BTC": Decimal("5")}, "w")), 1)


if __name__ == "__main__":
    unittest.main()
