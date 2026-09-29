# koinly

Free tools and examples for Koinly custom CSV imports. Turn exchange exports and on-chain
history that Koinly does not support into files that import cleanly the first time.
Community tool, not affiliated with Koinly. Not tax advice.

| Project | What it does |
|---|---|
| [koinly-custom-csv](koinly-custom-csv/) | Builds Koinly Universal CSV files from exchange exports and blockchain history, checks them before you import, and predicts which transfers Koinly will merge and why others will not. First adapters: SafeTrade and Quantus (QTC), plus an ERC-20 check on EVM chains. Python standard library only; nothing is uploaded anywhere. |

By popek_1990 - [x.com/popek_1990](https://x.com/popek_1990) · [github.com/popek1990](https://github.com/popek1990)

MIT License. See [LICENSE](LICENSE). Koinly's own templates in
`koinly-custom-csv/templates/koinly/` belong to Koinly and are not covered by it.
