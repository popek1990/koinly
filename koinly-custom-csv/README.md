# Koinly custom CSV

Build Koinly Universal CSV files from exchange exports and blockchain history that Koinly does
not import on its own, check them before import, and predict which transfers Koinly will merge.

## What it does and why

Koinly has direct connections to some exchanges and blockchains but not all. If you trade on
SafeTrade, hold coins on Quantus, or use an EVM chain that Koinly does not sync directly, you
can export your history and turn it into a CSV file that Koinly's Universal template accepts.

This tool reads your exports, checks them for errors (wrong columns, repeated rows, bad balances),
and writes Koinly files in the exact format Koinly needs. It also predicts which transfers Koinly
will merge as a single transaction and warns you if a transfer cannot be merged (for example, a
withdrawal to an address Koinly does not know about).

Nothing is ever uploaded. The tool reads only from public endpoints and your local files.

## Requirements

- **Python 3.11 or later**
- Standard library only — no install step, no dependencies

Download the repository and work from the `koinly-custom-csv/` folder.

## Quick start

Try the example with invented data. From the `koinly-custom-csv/` folder:

```bash
python3 tools/koinlycsv.py build --config examples/safetrade-quantus/config.toml
```

The tool creates two CSV files (and their UTC copies) in `examples/safetrade-quantus/output/`.
The start of the summary (long lines shortened):

```text
Quantus wallet: 4 rows, final balance 36.274149423358 ID:56784085
SafeTrade: 13 rows, final balance 0.37 ID:56784085, 0 USDC:0xaf88...5831, 3.226481181 USDT:0xfd08...cbb9
Transfers Koinly should merge: 5
  Quantus wallet withdrawal 38.363 ID:56784085 at 2026-03-26 13:51:34 UTC (...)  >>  SafeTrade deposit 38.363 ...
  ...
OK: 0 error(s), 1 warning(s)
```

The warning is about a withdrawal to a wallet that is not in Koinly: Koinly will treat it as a
sale (a "broken transfer"). The other five transfers pass all of Koinly's matching rules.
See [the example's README](examples/safetrade-quantus/README.md) for the story behind the data.

## Using your own data

1. Create a `private/` folder (it is ignored by git):

   ```bash
   mkdir private
   cp tools/config.example.toml private/config.toml
   ```

2. Edit `private/config.toml`:
   - Set the time zone (e.g. `Europe/London`, `America/New_York`, or `UTC`).
   - List your addresses under `[[wallets]]`.
   - Map currency codes to Koinly notation (see `tools/config.example.toml` for examples).

3. Fetch on-chain history (read-only):

   ```bash
   python3 tools/koinlycsv.py fetch --config private/config.toml
   ```

   This reads the public Quantus indexer and the EVM RPC and saves snapshots where your config
   says. The build then works from these snapshots only, so it gives the same result every time.

4. Build CSV files:

   ```bash
   python3 tools/koinlycsv.py build --config private/config.toml
   ```

5. Review the summary: note every transfer Koinly should merge and every warning.

6. Import into Koinly (see "Importing into Koinly" below).

## What the build checks

If any check fails with an error, nothing is written.

- **Currencies:** every currency is valid Koinly notation (`BTC`, `ID:<number>`,
  `SYMBOL:CONTRACT`); exchange codes must be mapped in the config, so SafeTrade's `QTC`
  (Qubitcoin) cannot pass as Quantus.
- **Tags:** only Koinly's tags, and only on the row type they belong to.
- **Hashes:** a transaction hash appears once per file.
- **Running balance:** no currency in any wallet ever goes below zero.
- **Expected balance:** the final balance equals what you say the exchange shows, and for
  Quantus what the chain shows.
- **EVM check:** exchange withdrawals and deposits of USDT/USDC match the chain in amount and
  time, and go to wallets that Koinly knows.
- **Transfers:** Koinly's six matching rules (same currency, at most 12 hours apart, withdrawal
  first, deposit not larger and at most 20% smaller, same hash or at least one side without a
  hash). Every near miss is explained, e.g. a deposit that looks an hour early because of a
  wrong time zone.
- **Time zones:** a warning for local times that happen twice when clocks go back.
- **Read-back:** each written file is read again and must match what was meant.
- **Manual rows:** rows you typed in are skipped when the export already has them.

## Importing into Koinly

1. Create one wallet in Koinly for each file (e.g. "Quantus", "SafeTrade").

2. Import from file, and choose the **time zone** that matches `timezone` in your config. The
   label may show the winter offset (e.g. "(GMT+00:00) London"), which is normal.
   - **Alternative:** Import files from `output/utc/` and choose "Auto-detect / UTC".

3. Use the checklist in `docs/after-import-checklist.md`. The most important test is a transfer
   between a CSV wallet and a wallet Koinly syncs itself (e.g. an exchange withdrawal to an EVM
   address Koinly tracks). It must show as a single transfer (`>>`), not separate withdrawal and
   deposit. If it does not, delete the CSV wallets and import again with the other time zone or
   the UTC files.

## Supported sources

| Source | Type | How to use |
|---|---|---|
| **SafeTrade** | Exchange export | `adapter = "safetrade"` in the config; export trades and transactions from the web panel |
| **Quantus (QTC)** | Public blockchain indexer | `adapter = "quantus"` in the config; list your addresses |
| **EVM chains** | Public JSON-RPC check | `[evm]` section in the config; checks ERC-20 deposits and withdrawals (example: USDT and USDC on Arbitrum One) |

Learn more: [docs/exchanges/safetrade.md](docs/exchanges/safetrade.md),
[docs/chains/quantus.md](docs/chains/quantus.md), and
[docs/writing-an-adapter.md](docs/writing-an-adapter.md) for other sources.

## Documentation

- [docs/koinly-csv-rules.md](docs/koinly-csv-rules.md): Koinly's CSV rules, each with a source
  (checked 2026-09-29).
- [docs/after-import-checklist.md](docs/after-import-checklist.md): what to check in Koinly after
  the import.
- [docs/exchanges/safetrade.md](docs/exchanges/safetrade.md): SafeTrade exports and currency codes.
- [docs/chains/quantus.md](docs/chains/quantus.md): Quantus (QTC) in Koinly and the indexer.
- [docs/writing-an-adapter.md](docs/writing-an-adapter.md): adding an exchange or a blockchain.
- [MAP.md](MAP.md): what each file is for.
- [skills/koinly-csv/SKILL.md](skills/koinly-csv/SKILL.md): a Claude Code skill for the same workflow.

## Testing

All adapters are tested with invented data (fake addresses, fake hashes, invented amounts). Run the
tests from the `koinly-custom-csv/` folder:

```bash
python3 -m unittest discover -s tools
```

To regenerate the example output (if the inputs change), run:

```bash
python3 tools/make_example.py
```

Then commit the new `examples/` files.

## License and disclaimer

MIT license (see [../LICENSE](../LICENSE)). Koinly's own CSV templates in `templates/koinly/` are excluded
and remain the property of Koinly; see [templates/koinly/SOURCES.md](templates/koinly/SOURCES.md).

**These tools write tags to your CSV file, but they do not decide taxes.** What a tag means for
your taxes depends on your Koinly settings, your country and your situation. This is not tax
advice. Community tool, not affiliated with Koinly, SafeTrade or the Quantus team.
