"""Tests for the prediction of Koinly's transfer matching. All data is invented."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from koinly_csv.transfers import Leg, match, near_misses, rule_failures

T = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)


def leg(wallet, direction, minutes, amount, currency="ETH", tx_hash=""):
    return Leg(wallet, direction, T + timedelta(minutes=minutes), Decimal(amount), currency, tx_hash)


class RuleTests(unittest.TestCase):
    def test_all_rules_pass(self):
        self.assertEqual(rule_failures(leg("A", "out", 0, "1"), leg("B", "in", 5, "0.99")), [])

    def test_each_rule(self):
        out = leg("A", "out", 0, "1", tx_hash="0x1")
        self.assertIn("different currency", rule_failures(out, leg("B", "in", 5, "1", "BTC"))[0])
        self.assertIn("more than 12 hours", rule_failures(out, leg("B", "in", 12 * 60 + 1, "1"))[0])
        self.assertIn("larger", rule_failures(out, leg("B", "in", 5, "1.01"))[0])
        self.assertIn("20%", rule_failures(out, leg("B", "in", 5, "0.79"))[0])
        self.assertIn("hashes", rule_failures(out, leg("B", "in", 5, "1", tx_hash="0x2"))[0])

    def test_wrong_time_zone_is_recognised(self):
        # The deposit arrived 5 minutes after the withdrawal, but the exchange file was read an hour late.
        reasons = rule_failures(leg("A", "out", 60, "1"), leg("B", "in", 5, "1"))
        self.assertIn("wrong time zone", reasons[0])


class MatchTests(unittest.TestCase):
    def test_hash_wins_over_time(self):
        out = leg("A", "out", 0, "1", tx_hash="0x9")
        near = leg("B", "in", 1, "1")
        hashed = leg("C", "in", 30, "1", tx_hash="0x9")
        result = match([out, near, hashed])
        self.assertEqual(result.pairs, [(out, hashed)])
        self.assertEqual(result.unmatched, [near])

    def test_same_wallet_is_never_a_transfer(self):
        result = match([leg("A", "out", 0, "1"), leg("A", "in", 1, "1")])
        self.assertEqual(result.pairs, [])

    def test_near_miss_explains_a_failed_pair(self):
        out = leg("A", "out", 60, "1", tx_hash="0x1")
        inc = leg("B", "in", 5, "1", tx_hash="0x1")
        self.assertEqual(match([out, inc]).pairs, [])
        misses = near_misses(out, [out, inc])
        self.assertEqual(misses[0][0], inc)
        self.assertIn("before the withdrawal", misses[0][1][0])

    def test_different_hashes_are_not_a_near_miss(self):
        out = leg("A", "out", 0, "1", tx_hash="0x1")
        self.assertEqual(near_misses(out, [out, leg("B", "in", 5, "1", tx_hash="0x2")]), [])


if __name__ == "__main__":
    unittest.main()
