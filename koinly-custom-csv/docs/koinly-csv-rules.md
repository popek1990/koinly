# Koinly CSV rules

What Koinly expects from a custom CSV file, with a source for every rule.
All articles were read on **2026-09-29**. Koinly can change them, so check the article
before you rely on a rule for something important.

Rules marked **Tested** come from a real import, not from Koinly's documentation.

| Short name | Article |
|---|---|
| custom CSV | [How to create a custom CSV file with your data](https://support.koinly.io/en/articles/9489976-how-to-create-a-custom-csv-file-with-your-data) |
| transfers | [How Koinly handles transfers between your own wallets](https://support.koinly.io/en/articles/9490024-how-koinly-handles-transfers-between-your-own-wallets) |
| broken transfers | [Transfers between my own wallets are showing gains (or losses)](https://support.koinly.io/en/articles/9490066-transfers-between-my-own-wallets-are-showing-gains-or-losses) |
| time zone import | [How to import a CSV file using a different timezone](https://support.koinly.io/en/articles/9489985-how-to-import-a-csv-file-using-a-different-timezone) |
| time zone detection | [CSV import: timestamps are not in UTC timezone](https://support.koinly.io/en/articles/9490014-csv-import-timestamps-are-not-in-utc-timezone) |
| prices | [How Koinly sets the market price for your transactions](https://support.koinly.io/en/articles/9489964-how-koinly-sets-the-market-price-for-your-transactions) |

## 1. Which template

Koinly has three templates (custom CSV):

- **Simple**: deposits, withdrawals, rewards;
- **Trades**: trades only;
- **Universal**: deposits, withdrawals and trades in one file.

These tools always write **Universal**. The Trades template cannot pin a token by contract or
Koinly ID, because its `Pair` column "does not support the extended notation" (custom CSV).

## 2. Universal columns

Required, with these exact names (custom CSV):

| Column | Content |
|---|---|
| `Date` | `YYYY-MM-DD HH:mm:ss`, e.g. `2025-11-25 13:22:10` |
| `Sent Amount` | dot as the decimal separator; **gross**, the fee is not deducted |
| `Sent Currency` | symbol or extended notation (section 3) |
| `Received Amount` | dot as the decimal separator; **gross** |
| `Received Currency` | symbol or extended notation |

Optional: `Fee Amount`, `Fee Currency`, `Net Worth Amount`, `Net Worth Currency` (fiat only),
`Fee Worth`, `Tag`, `Description`, `TxHash`.

Which cells to fill:

| Row | Sent | Received |
|---|---|---|
| deposit | empty | filled |
| withdrawal | filled | empty |
| trade | filled | filled |

Common reason for "unknown file": a column name that is not exact. `Koinly Date` is correct in
the Simple and Trades templates only; Universal uses `Date` (custom CSV).

**Gross amounts and a separate fee** mean this for the balance:

- withdrawal: the wallet loses `Sent Amount` + `Fee Amount`;
- trade with the fee in the bought token: the wallet gains `Received Amount` − `Fee Amount`.

The build uses exactly this rule for its running balance check.

## 3. Currency notation

Several tokens can share a symbol. With a plain symbol, Koinly picks "the most popular token
with the particular symbol" (custom CSV). To choose the token yourself:

| Form | Example | Where the value comes from |
|---|---|---|
| `SYMBOL:CONTRACT_ADDRESS` | `USDT:0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9` | the token contract |
| `SYMBOL:CONTRACT_ADDRESS:BLOCKCHAIN` | `WIF:EKpQ...zcjm:SOL` | contract plus the chain's native currency |
| `ID:<number>` | `ID:18431515` | the number in the URL of the token on Koinly's Markets page |

**Tested:** USDT written as `USDT:<Arbitrum One contract>` in a CSV wallet merged into transfers
with deposits in an EVM wallet that Koinly syncs itself. Both sides have to name the same
token, or the likeness check fails (section 5).

## 4. Tags

One tag per row. Tags from the custom CSV article:

| Row | Tags |
|---|---|
| deposit | `other income`, `reward`, `mining`, `airdrop`, `fork`, `salary`, `lending interest`, `loan`, `marg loan`, `realized gain`, `futures fee`, `funding fee`, `unstake`, `cashback`, `fee refund` |
| withdrawal | `cost`, `other fee`, `margin fee`, `loan fee`, `loan repayment`, `margin repayment`, `lost`, `gift`, `donation`, `realized gain`, `futures fee`, `funding fee`, `stake` |
| trade | `liquidity in`, `liquidity out` (LP tokens only) |

- Rows tagged `stake` or `unstake` are skipped on import.
- `swap` is ignored in a CSV; you can add it in Koinly after the import.
- A standalone fee is a withdrawal with a cost tag, e.g. `cost`. The Quantus adapter writes the
  network fee of a move between your own addresses this way.

What a tag means for your taxes depends on your Koinly settings and your country.
These tools do not decide that, and nothing here is tax advice.

## 5. Transfers between your own wallets

Koinly merges a withdrawal from wallet A and a deposit into wallet B into one transfer when all
of these hold (transfers):

1. **likeness:** the same asset;
2. **interval:** within 12 hours of each other;
3. **chronology:** the withdrawal happens before the deposit;
4. **amount:** the deposit is equal to or smaller than the withdrawal;
5. **difference:** the deposit is at most 20% smaller;
6. **hash:** the same transaction hash, or at least one side has no hash.

A leg without a pair is a **broken transfer**: the withdrawal counts as a sale at market price,
the deposit as a purchase at market price (broken transfers). Koinly's advice for transfers that
did not merge is to fix the data at the source, usually by re-importing with the right time zone,
not by editing transactions (transfers).

The build predicts these pairs with the same six rules (`tools/koinly_csv/transfers.py`) and
explains every near miss, for example "the deposit is 55m before the withdrawal (close to a
whole number of hours: probably a file imported in the wrong time zone)".

## 6. Time zones

- Koinly treats dates without an offset as UTC, unless the file states its zone in the headers
  or in the fields (time zone detection).
- In the import dialog you can pick the zone the file is written in, instead of
  "Auto-detect / UTC" (time zone import).
- The app shows times in UTC; reports use the zone from your account settings (time zone import).
- **Tested:** the dialog labels zones with their winter offset, e.g. "(GMT+00:00) London". A file
  written in summer time in a European zone with daylight saving, imported with that zone picked,
  was still read with the summer offset: its transfers merged with a wallet that Koinly syncs itself.

Two traps these tools guard against:

1. **A wrong zone can hide.** If two CSV wallets are both read an hour off, transfers between
   them still merge, because both sides moved together. Only a transfer between a CSV wallet and
   a wallet Koinly syncs itself shows the mistake ("our API always imports timestamps as UTC",
   time zone import). Check one of those first after an import
   ([after-import-checklist.md](after-import-checklist.md)).
2. **The hour that happens twice.** When clocks go back, local times in that hour exist twice
   and a file cannot say which one it means. The build warns about such rows. For that period,
   import the UTC copy instead.

The build writes each file in the zone from your config and, by default, a UTC copy in
`output/utc/`. Pick the same zone in the dialog, or import the UTC copy with "Auto-detect / UTC".

## 7. Prices

- Crypto–fiat trades: the fiat side sets the value (prices).
- Crypto–crypto trades: Koinly uses average market rates from aggregators such as CoinGecko or
  CoinMarketCap. The transaction details show the source and which asset's price was used (prices).
- A token that no aggregator lists gets a "Missing market price" warning. `Net Worth Amount`
  and `Net Worth Currency` let a CSV carry the value itself (custom CSV).
- **Tested:** a QTC → USDT trade was valued by its USDT side.

## 8. Missing purchase history

Koinly names wrong time zones as a cause of missing purchase history errors (time zone import).
A related cause is a wallet that spends more than it holds at that moment. The build keeps a
running balance for every currency in every wallet and stops before writing if it ever goes
below zero.
