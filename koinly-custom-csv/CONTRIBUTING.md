# Contributing

Thank you for helping. Here are the guidelines.

## Reporting a changed export format

If an exchange's export format has changed (for example, SafeTrade added a new column or renamed
one), open an issue with:

1. The adapter name (e.g. `safetrade`).
2. The exact header line of the new export, copied and pasted.
3. **Never include any data rows, amounts, times, hashes or addresses** — not even anonymised
   ones. Real amounts and times identify transactions on public chains, so "anonymised" data can
   still leak privacy.

The tool recognises exports by their header, so the issue helps us add support for the new format.

## Adding an exchange or a blockchain

Follow `docs/writing-an-adapter.md`:

1. Create `tools/adapters/<name>.py` with a `load_rows()` function and optionally a `fetch()` for
   network data.
2. Add the name to `ADAPTERS` in `tools/koinly_csv/config.py` and to `_adapter()` in
   `tools/koinly_csv/build.py`.
3. Write tests in `tools/tests/test_<name>.py` using **invented data only**:
   - Fake addresses that look fake at a glance (`qzEXAMPLE...`, `0x000...a1`).
   - Fake transaction hashes (mostly zeros is fine).
   - Invented amounts, for example from a random generator with a fixed seed, as `tools/make_example.py` does.
   - Never paste real rows from an export, even if the addresses or amounts have been changed.

   **Why?** Amounts and times identify transactions on a public blockchain. "Anonymised" real data
   can still leak the holder's transaction history and activity patterns, even if the holder is
   not identified by name. For example, a real amount like 12.34567 QTC bought for 123.4567 USDT
   at 2026-03-26 12:34:56 UTC is a unique fingerprint on the chain.

4. Create `docs/exchanges/<name>.md` or `docs/chains/<name>.md` describing the export format,
   how to find your address or account ID, and any special rules.

5. Run all tests:

   ```bash
   python3 -m unittest discover -s tools
   ```

6. If the example input files change, regenerate the example output:

   ```bash
   python3 tools/make_example.py
   ```

   Commit the regenerated `examples/` files.

## Code style

- Python 3.11+ only. Use the standard library only — no external dependencies.
- Type hints where they make the code clearer.
- Decimal for amounts (never float).
- If the code reads network data, it must return a snapshot that `load_rows()` can read offline.

## Updating Koinly's rules

Every rule in `docs/koinly-csv-rules.md` cites an article from Koinly's help center
(`https://support.koinly.io/en/articles/<number>-...`). When a rule changes:

1. Read the current article and note the date you checked it.
2. Update the rule and its date in `docs/koinly-csv-rules.md`.
3. Update the module that enforces it (`tags.py`, `currencies.py`, `transfers.py`,
   `universal.py`) and its tests.

A rule that Koinly does not document can be added only as **Tested**: say what was imported and
what Koinly did, without any real data.

## Tips for tests

- Use `unittest` (standard library). Name test files `test_<subject>.py`.
- Tests never touch the network: adapters read local snapshots, and tests build those from invented data.
- Test both success and failure cases.
- Tests run from the `koinly-custom-csv/` folder.

## Commits and pull requests

- Keep commits small and focused.
- Use clear commit messages that say what changed and why.
- Tests must pass before you push: `python3 -m unittest discover -s tools`.
- The example must be up to date: if inputs change, run `python3 tools/make_example.py` and
  commit the new output.

## Questions?

Open an issue. This is a community tool, not affiliated with Koinly, SafeTrade or the Quantus team.
