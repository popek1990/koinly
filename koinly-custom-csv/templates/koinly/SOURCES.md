# Koinly templates: sources

These three files are Koinly's own custom CSV templates, kept here as reference material.
They belong to Koinly and are **not** covered by this repository's MIT license.

Downloaded on 2026-09-29 from the Google Sheets linked in Koinly's help article
[How to create a custom CSV file with your data](https://support.koinly.io/en/articles/9489976-how-to-create-a-custom-csv-file-with-your-data):

| File | Template | Source sheet |
|---|---|---|
| `koinly-simple-template.csv` | Simple | https://docs.google.com/spreadsheets/d/1XCDApE_FaBR9mNIv_Xtk-3yRKRGo-gCIzh1vsKz9OdE |
| `koinly-trades-template.csv` | Trades | https://docs.google.com/spreadsheets/d/1GbZXm0INfBn3sXKwcEuCKBDQUSxwSOKfZt7Ndy9l35M |
| `koinly-universal-template.tsv` | Universal | https://docs.google.com/spreadsheets/d/1fMfSNy0mVimjwpiWmIDdsU9BdOXMX7EbpWVUgRmUXg0 |

Each file is the sheet's own CSV or TSV export (`/export?format=csv` or `format=tsv`), unchanged.
The Universal sheet exports as TSV; Koinly accepts the same columns in a CSV file.

Headers:

```text
Simple:     Koinly Date, Amount, Currency, Tag, Description
Trades:     Koinly Date, Pair, Side, Amount, Total, Fee Amount, Fee Currency
Universal:  Date, Sent Amount, Sent Currency, Received Amount, Received Currency,
            Fee Amount, Fee Currency, Tag, Description
```

The templates show only some of the optional columns. The full list for each template is in
the help article above and in [../../docs/koinly-csv-rules.md](../../docs/koinly-csv-rules.md).
