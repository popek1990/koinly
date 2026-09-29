# Example: SafeTrade + Quantus (invented data)

Everything in this folder is made up by `tools/make_example.py` with a fixed seed: addresses
(`qzEXAMPLE...`, `0x000...a1`), hashes (mostly zeros), amounts and times. None of it is a real
transaction.

## The story

| When (UTC) | What happens | What it shows |
|---|---|---|
| 26 Mar | an airdrop pays two of your Quantus addresses in one batch | one `airdrop` row with the sum |
| 26 Mar | QTC moves from your address to SafeTrade | a transfer Koinly merges by hash |
| 26 Mar | QTC sold for USDT, the first order in two fills | trades with the fee in USDT |
| 27 Mar | USDC deposited from your EVM wallet, sold for USDT | an EVM wallet already in Koinly |
| 29 Mar, 00:48 | USDT withdrawn the night clocks go forward in Europe | local times jump from +01:00 to +02:00 |
| 30 Mar | QTC bought back and withdrawn to your second address | a withdrawal fee charged on top |
| 31 Mar | QTC moved between your own addresses | only the network fee, tagged `cost` |
| 1 Apr | USDT withdrawn to a wallet that is not in Koinly | a "broken transfer" warning |
| 2 Apr | a withdrawal the export does not have yet, typed in by hand | a manual file in local time |

The typed-in file also repeats the 29 March withdrawal; the build skips it as a duplicate.

## Try it

From the `koinly-custom-csv` folder:

```bash
python3 tools/koinlycsv.py build --config examples/safetrade-quantus/config.toml
```

The files appear in `examples/safetrade-quantus/output/` (ignored by git) and must be identical
to `expected/`. The build predicts 5 merged transfers, prints one "broken transfer" warning and
reports the balances.

| Folder | Content |
|---|---|
| `input/safetrade/` | the two SafeTrade exports (dates in UTC) |
| `input/manual/` | rows typed in by hand (dates in Europe/Berlin) |
| `input/quantus-snapshot.json` | what `fetch` saves from the Quantus indexer |
| `input/evm-snapshot.json` | what `fetch` saves from the EVM chain |
| `expected/` | the Koinly files in Europe/Berlin time; `expected/utc/` in UTC |
