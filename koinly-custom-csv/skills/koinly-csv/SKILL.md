---
name: koinly-csv
description: Build Koinly custom CSV files (Universal template) from exchange exports and blockchain history that Koinly does not import on its own, check them before import, and explain what Koinly will do with them. Use when someone wants to get SafeTrade, Quantus (QTC) or another unsupported exchange or chain into Koinly, when a Koinly CSV import fails or shows unmatched transfers, or when adding a new adapter to koinly-custom-csv.
---

# Koinly custom CSV

Tools live in `koinly-custom-csv/tools/` (Python 3.11+, standard library only).
Koinly's rules, each with a source link: `koinly-custom-csv/docs/koinly-csv-rules.md`.

## Ground rules

- The user's data stays on their computer, in `koinly-custom-csv/private/` (ignored by git).
  Never copy their addresses, hashes, amounts or exports into tracked files, commits, issues or
  examples. "Anonymised" real amounts still identify transactions on a public chain.
- Never ask for seed phrases, private keys or exchange API secrets. Nothing here needs them.
- These tools write tags; they do not decide taxes. Do not give tax advice.
- Run commands from the `koinly-custom-csv` folder.

## Workflow

1. **Collect inputs** into `private/`: exchange exports (e.g. SafeTrade trades and transactions
   CSV files) and the list of the user's own addresses.
2. **Write the config**: copy `tools/config.example.toml` to `private/config.toml`.
   A complete example with invented data: `examples/safetrade-quantus/config.toml`.
   - `timezone`: the zone the output will be written in; the user must pick the same zone in
     Koinly's import dialog. UTC is the safest choice.
   - `[assets]`: exact Koinly notation, `ID:<number>` or `SYMBOL:CONTRACT`. Quantus is
     `ID:56784085`. On SafeTrade the code for Quantus is `QUANTUS`; `QTC` there is Qubitcoin.
   - `expected_balances`: ask the user for the balances the exchange shows now.
3. **Fetch** on-chain snapshots (read-only, public endpoints):
   `python3 tools/koinlycsv.py fetch --config private/config.toml`
4. **Build**: `python3 tools/koinlycsv.py build --config private/config.toml`
   - Errors stop the build before anything is written. Fix the cause in the input or config;
     never edit the output files by hand.
   - Read every warning to the user, especially "will NOT merge" (a transfer Koinly will not
     match, with the failed rule) and "broken transfer" (a destination wallet that is not in
     Koinly).
5. **Import**: one Koinly wallet per file in `private/output/`, zone as in the config, or the
   `output/utc/` copies with "Auto-detect / UTC".
6. **Verify** with `docs/after-import-checklist.md`. The decisive test is one transfer between
   a CSV wallet and a wallet Koinly syncs itself: it must be merged (`>>`). Transfers between two
   CSV wallets still merge when both are read in the wrong zone, so they prove nothing.

## Checking a file made elsewhere

`python3 tools/koinlycsv.py validate FILE [FILE...] --timezone <zone the dates are in>`
checks format, currencies, tags, repeated hashes, running balances and, with several files,
which transfers Koinly should merge.

## Diagnosing a failed import

| Symptom | Likely cause | Where to look |
|---|---|---|
| "unknown file" | a column name is not exact, e.g. `Koinly Date` in Universal | rules §2 |
| transfers not merged, deposit an hour "before" the withdrawal | wrong zone at import | rules §5, §6 |
| grey currency icon or a wrong coin | plain symbol; use `ID:` or `SYMBOL:CONTRACT` | rules §3 |
| missing purchase history | missing deposit, rows out of order or wrong zone | rules §8 |
| a withdrawal counted as a sale | the other wallet is not in Koinly (broken transfer) | rules §5 |

## Adding an exchange or a chain

Follow `docs/writing-an-adapter.md`: one file in `tools/adapters/`, tests with invented data
only, and a page in `docs/exchanges/` or `docs/chains/`. Run
`python3 -m unittest discover -s tools` before finishing. If the example inputs change, run
`python3 tools/make_example.py` and commit the regenerated `examples/` files.
