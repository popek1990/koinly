# Writing an adapter

An adapter turns one exchange's export or one chain's history into Koinly rows. Everything
else (checks, transfer prediction, writing, the UTC copy) is shared, so a new adapter is
usually one file plus tests.

## The contract

Create `tools/adapters/<name>.py` with:

```python
def load_rows(wallet: WalletConfig, config: Config) -> tuple[list[Row], list[Issue]]:
    ...
```

- `wallet.options` holds every key of the wallet's `[[wallets]]` table that the core does not
  use itself (`name`, `adapter`, `output`, `manual_files` and `expected_balances` are core keys).
- `config.resolve(path)` turns a path from the config into an absolute path.
- `config.currency(asset_key)` gives the Koinly notation from `[assets]`.

Then add the name to `ADAPTERS` in `tools/koinly_csv/config.py` and to `_adapter()` in
`tools/koinly_csv/build.py`. If the source needs the network, add a `fetch(wallet, config)`
that writes a local snapshot, and call it from `command_fetch` in `tools/koinlycsv.py`.
`load_rows` itself must never touch the network: a build has to be repeatable.

## Rules for rows

| Rule | Why |
|---|---|
| `Row.time` is timezone-aware, normally UTC | the writer converts to the output zone |
| amounts are gross, the fee goes in `fee` | Koinly's Universal rule; the balance check relies on it |
| use `Decimal`, never `float` | exact amounts; the build compares balances to the last digit |
| a stable, unique `tx_hash` per row | lets Koinly match transfers and lets the build find duplicates |
| no tag on transfers between wallets | tagged rows are never matched as transfers |
| at the same second: deposits, then trades, then withdrawals | the running balance never dips below zero by accident |
| report problems as `Issue`, do not guess | an `error` stops the build before anything is written |

## Tests

Add `tools/tests/test_<name>.py` with invented data only: fake addresses such as
`qzEXAMPLE...` or `0x000...a1`, hashes that are mostly zeros, invented amounts. Never paste rows
from a real export, not even "anonymised": amounts and times identify transactions on a public
chain.

Run all tests from the `koinly-custom-csv` folder:

```bash
python3 -m unittest discover -s tools
```

## Documentation

Add `docs/exchanges/<name>.md` or `docs/chains/<name>.md`: the export's header line, the time
zone of its dates, how fees work, currency codes that could be confused, and the date you
checked all this.
