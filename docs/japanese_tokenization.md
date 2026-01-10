# Japanese Tokenization & Internationalization

## Overview

The search engine supports identifying and tokenizing Japanese text to provide accurate search results. This is achieved by combining **SudachiPy** (morphological analyzer) with **SQLite FTS5**.

## Implementation Details

### 1. Tokenizer: SudachiPy (Shared Logic)
Unlike English, Japanese text does not use spaces to separate words. We use **SudachiPy** with the `sudachidict_core` dictionary to split Japanese sentences into tokens.

**Code Location**: `shared/src/shared/analyzer.py`

When a Japanese sentence like `東京都へ行く` is processed, it is converted to space-separated tokens: `東京都 へ 行く`.

This logic is centralized in the **Shared Library** because it must be identical for both:
*   **Indexer Service**: When saving content to the DB.
*   **Frontend Service**: When parsing user search queries.

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
When a user searches for a query, the same `JapaneseAnalyzer` from `shared` is applied to the query string *before* it is sent to the database.

*   User Query (Raw): `東京へ`
*   Analyzed Query: `東京 OR へ` (or just `東京 へ`)
*   SQL Query: `MATCH '東京 へ'`

## Development Notes

*   **Dictionary**: The project uses `sudachidict_core` by default.
*   **Performance**: Tokenization happens in-memory (Python) before DB insertion.
