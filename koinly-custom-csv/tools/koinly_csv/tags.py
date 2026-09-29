"""Tags Koinly accepts in the Tag column of a CSV import.

Source: Koinly help article 9489976, section "Tags to use in CSVs" (checked 2026-09-29).
Only one tag per row.
"""
from __future__ import annotations

DEPOSIT_TAGS = frozenset({
    "other income", "reward", "mining", "airdrop", "fork", "salary", "lending interest",
    "loan", "marg loan",
    "realized gain", "futures fee", "funding fee",
    "unstake",  # Koinly skips these rows on import
    "cashback", "fee refund",
})

WITHDRAWAL_TAGS = frozenset({
    "cost", "other fee", "margin fee", "loan fee",
    "loan repayment", "margin repayment",
    "lost", "gift", "donation",
    "realized gain", "futures fee", "funding fee",
    "stake",  # Koinly skips these rows on import
})

TRADE_TAGS = frozenset({"liquidity in", "liquidity out"})

SKIPPED_ON_IMPORT = frozenset({"stake", "unstake"})


def tag_problem(tag: str, kind: str) -> tuple[str, str] | None:
    """Return (level, message) when `tag` does not fit a row of `kind`, else None."""
    if not tag:
        return None
    if tag == "swap":
        return "warning", "the swap tag is ignored by CSV import; add it in Koinly after importing"
    allowed = {"deposit": DEPOSIT_TAGS, "withdrawal": WITHDRAWAL_TAGS, "trade": TRADE_TAGS}[kind]
    if tag in allowed:
        if tag in SKIPPED_ON_IMPORT:
            return "warning", f"Koinly skips rows tagged {tag!r} on import"
        return None
    known = DEPOSIT_TAGS | WITHDRAWAL_TAGS | TRADE_TAGS
    if tag in known:
        return "error", f"tag {tag!r} does not apply to a {kind}"
    if tag.lower() in known:
        return "warning", f"tag {tag!r} differs in letter case from Koinly's {tag.lower()!r}"
    return "error", f"unknown tag {tag!r}"
