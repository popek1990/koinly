# Quantus (QTC)

[Quantus](https://quantus.com) is a post-quantum blockchain. Koinly does not sync it, so the
`quantus` adapter builds a Koinly file from the public indexer.

## Name and ticker in Koinly

| Where | Name |
|---|---|
| Quantus itself | Quantus, ticker **QTC** |
| Koinly | "Quantus Network (QUAN)", **`ID:56784085`** (QUAN is the ticker from its testnet era) |
| SafeTrade | code `QUANTUS` (`QTC` on SafeTrade is Qubitcoin) |

Write QTC as `ID:56784085`, never as the plain symbol `QTC`: that symbol belongs to other coins.
The ID is the number in the URL `app.koinly.io/p/markets/56784085`; the Markets page needs a
Koinly login. Checked on 2026-09-29.

```toml
[assets]
QTC = "ID:56784085"
```

## Where the data comes from

`koinlycsv.py fetch` reads the public indexer `https://sqm.quantus.com/v1/graphql`. It saves
every transfer from or to your addresses up to one pinned block, plus the balances of your
addresses, into a local JSON snapshot. The build works from that snapshot only, so running it
twice gives the same files.

| Indexer field | Use |
|---|---|
| `amount`, `fee` | integers in planck; 1 QTC = 10^12 planck |
| `fee` | the network fee paid by the sender; counted only when the sender is yours |
| `extrinsic_id` | the transaction hash; SafeTrade shows the same value as `TxHash` |
| `timestamp` | UTC |

If your addresses move while the snapshot is being made, `fetch` starts again (up to three times).

## How transfers become rows

All addresses in `addresses` form one Koinly wallet.

| On chain | Row |
|---|---|
| incoming from someone else | deposit |
| incoming from an address in `sender_tags` | deposit with that tag, e.g. `airdrop` |
| outgoing to someone else | withdrawal, with the network fee in `Fee Amount` |
| between two of your addresses | only the network fee, as a withdrawal tagged `cost` |
| one extrinsic paying several of your addresses (a batch) | one row with the sum |

A transaction hash appears once per file, which is why a batch becomes one row.

## Airdrops

Airdrop payouts can arrive in batches. To tag them, put the paying address in `sender_tags`:

```toml
[wallets.sender_tags]
"qz...the address that paid your airdrop..." = "airdrop"
```

Find that address in your own airdrop transfer in a block explorer. What the tag means for your
taxes depends on your Koinly settings and your country; these tools only write it.

## The balance check

At the end, the file's balance must equal the balance of your addresses in the snapshot.
If it does not, the build stops. Usual reasons:

- an address of yours is missing from `addresses`;
- you paid fees for extrinsics that are not transfers;
- an address was emptied to below the existential deposit and the chain removed the remaining
  dust.

Find the difference in a block explorer and add it as a withdrawal in a manual file
(see [../exchanges/safetrade.md](../exchanges/safetrade.md#rows-missing-from-the-export) for the
format).

## Not covered yet

- Mining rewards and other newly minted coins: the indexer shows them as transfers from a
  special account, without an extrinsic hash. You can tag that account in `sender_tags`, but the
  adapter was not tested on mining history.
- Wormhole (private) transfers.

Community tool, not affiliated with the Quantus team or with Koinly.
