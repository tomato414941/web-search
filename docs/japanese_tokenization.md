# Japanese Tokenization & Internationalization

## Overview

The search engine supports identifying and tokenizing Japanese text to provide accurate search results. This is achieved by combining **SudachiPy** (morphological analyzer) with **SQLite FTS5**.

## Implementation Details

### 1. Tokenizer: SudachiPy
Unlike English, Japanese text does not use spaces to separate words. We use **SudachiPy** with the `sudachidict_core` dictionary to split Japanese sentences into tokens.

**Code Location**: `src/web_search/indexer/analyzer.py`

When a Japanese sentence like `東京都へ行く` is indexed, it is converted to space-separated tokens: `東京都 へ 行く`.

### 2. Indexing Strategy (SQLite FTS5)
To support this pre-tokenized text, we use the FTS5 **`unicode61` tokenizer**.

```sql
CREATE VIRTUAL TABLE pages USING fts5(
  ...
  tokenize='unicode61'
);
```

The `unicode61` tokenizer splits text by whitespace and unicode boundaries. By feeding it the space-separated output from SudachiPy, we enable word-based matching for Japanese.

### 3. Query Processing
When a user searches for a query, the same `JapaneseAnalyzer` is applied to the query string *before* it is sent to the database.

*   User Query (Raw): `東京へ`
*   Analyzed Query: `東京 OR へ` (or just `東京 へ` depending on logic)
*   SQL Query: `MATCH '東京 へ'`

## Development Notes

*   **Dictionary**: The project uses `sudachidict_core` by default. It is installed via `pip`.
*   **Performance**: Tokenization happens in-memory (Python) before DB insertion.
