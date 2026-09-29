# After-import checklist

Use this list after `koinlycsv.py build` reports `OK` and you import the files into Koinly.
Sources for every rule are in [koinly-csv-rules.md](koinly-csv-rules.md).

## Before the import

1. Keep the build summary open. It lists every transfer Koinly should merge and every final
   balance.
2. Check your Koinly settings for how tags such as `airdrop` or `mining` are treated.
   These tools write the tag; your settings and your country decide what it means.

## The import

3. Create one wallet in Koinly for each file in `output/`, for example "Quantus wallet" and
   "SafeTrade". Choose a wallet without an API connection and import from a file.
4. In the **Timezone** field, pick the zone from `timezone` in your config. The label may show
   the winter offset, e.g. "(GMT+00:00) London" for Europe/London. That is expected.
   - Alternative: import the files from `output/utc/` with "Auto-detect / UTC".
   - Never mix the two: all files of one import use the same set.

## Right after the import

5. **The time zone test.** Open a transfer between a CSV wallet and a wallet Koinly syncs
   itself (API or address), e.g. an exchange withdrawal to your EVM wallet. It must show as
   one **transfer** line with the `>>` icon.
   - If it shows as a separate withdrawal and deposit, delete the CSV wallets and import again
     with the other file set (local zone ↔ `utc/`).
   - Do not repair it by editing transactions: Koinly's advice is to fix the data at the source.
     Editing a leg that already exists duplicates it.
   - Transfers between two CSV wallets are not a valid test: if both files are read an hour
     off, they still merge.
6. **Transfer count.** Compare the transfers Koinly merged with the list in the build summary.
   A missing pair usually means a missing wallet, a wrong zone or a different token on one side.
7. **Currencies.** No grey "unknown currency" icons, and every token is the one you meant.
   Example: QTC must be Quantus, not Qubitcoin (see [chains/quantus.md](chains/quantus.md)).

## Numbers

8. **Balances.** Each wallet's balance in Koinly equals the final balance in the build summary,
   and that equals what the exchange or the chain shows.
9. **Trade values.** Open one trade and check which asset's price Koinly used. For a token that
   aggregators do not list, the value should come from the other side of the trade.
10. **Tags.** Rows you tagged, e.g. `airdrop` or `cost`, show that tag in Koinly.
11. **Warnings the build printed.** Every "broken transfer" warning from the build appears in
    Koinly as a lone withdrawal or deposit, unless you add the missing wallet.

If something does not match, delete the wallet (its transactions go with it), fix the input or
the config, build again and re-import. Do not fix rows by hand in Koinly.
