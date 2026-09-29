# SafeTrade

[SafeTrade](https://safe.trade) is a small exchange that Koinly does not import on its own.
This page describes its CSV exports as seen in September 2026 and how the `safetrade` adapter
reads them. If your export looks different, open an issue with the header line
(never with your data).

## The two export files

| File | Header |
|---|---|
| trades (`snapshot-trades-<number>.csv`) | `Koinly Date,Pair,Side,Amount,Total,Fee Amount,Fee Currency,Order ID,Trade ID` |
| deposits and withdrawals (`snapshot-transactions-<number>.csv`) | `Koinly Date,Label,Currency,Amount,Fee Currency,Fee,TxHash` |

The number in the file name is a Unix timestamp of the moment the file was made. The adapter
recognises files by their header, so the names do not matter. You can point it at several
exports; a trade or transaction that appears in more than one is kept once, by `Trade ID` and
by `TxHash`.

## Why not import them into Koinly as they are

The headers look like Koinly's, but neither file fits a template exactly:

- trades: close to the Trades template, but `Pair` (e.g. `QUANTUS-USDT`) cannot carry a
  contract or `ID:` notation, so Koinly has to guess the token from SafeTrade's own code;
- transactions: close to the Simple template, but the fee column is `Fee` instead of
  `Fee Amount`, withdrawals have negative amounts and there is an extra `Label` column.

The adapter rewrites both into one Universal file with exact Koinly currencies.

## What the fields mean

| Field | Meaning |
|---|---|
| `Koinly Date` | **UTC.** The web panel shows the same rows in your local time. |
| `Pair` | `BASE-QUOTE`, e.g. `QUANTUS-USDT` |
| `Side` | `Buy` = base bought with quote, `Sell` = base sold for quote |
| `Amount` / `Total` | gross base amount / gross quote amount |
| `Fee Amount`, `Fee Currency` (trades) | the fee, charged in the currency you receive |
| `Label` | `Deposit` or `Withdrawal` |
| `Amount` (transactions) | positive for a deposit, negative for a withdrawal |
| `Fee` (transactions) | deposit: deducted from the amount that arrived; withdrawal: charged on top |
| `TxHash` | the on-chain hash; for Quantus it is the extrinsic hash from the indexer |

Fees change over time. The adapter takes every fee from its own row and never from a table.
Check the deposit fee against your balance after the import: the build's `expected_balances`
does this for you.

## Currency codes

SafeTrade uses its own codes. On SafeTrade **`QUANTUS` is Quantus, while `QTC` is Qubitcoin**,
a different coin. The adapter refuses any code that is not listed in `[wallets.symbols]` in your
config, so a mix-up cannot pass silently.

```toml
[wallets.symbols]
QUANTUS = "QTC"   # SafeTrade code -> your asset key
USDT = "USDT"
USDC = "USDC"
```

## Rows missing from the export

An export can end a little before the moment you made it. If recent rows are missing, type them
into a small file with Universal columns, in the time zone the panel showed, and add it as a
manual file:

```toml
manual_files = [{ path = "private/safetrade-typed-in.csv", timezone = "Europe/Berlin" }]
```

In that file you can write asset keys (`USDT`) instead of full Koinly notation. A typed-in row
whose `TxHash` is already in the export is skipped, so you can keep the file when a newer export
arrives. Rows without a hash are skipped only when time and amounts match an export row exactly.

## Withdrawals to an EVM chain

USDT and USDC withdrawals leave SafeTrade on an EVM chain (Arbitrum One in the example). With an
`[evm]` section, `fetch` reads every such transaction from the chain and the build checks:

- the on-chain amount equals the exchange amount;
- the block time is not earlier than the exchange time (Koinly's chronology rule);
- the destination is one of your `koinly_wallets`, otherwise a warning says the transfer will
  be broken.
