# Japanese Tokenization & Internationalization

## Overview
Japanese text is tokenized with **SudachiPy** before indexing and searching. Tokens are stored in the custom inverted index tables (not FTS5) so that the same analysis is used at index time and query time.

## Implementation Details

### 1. Tokenizer: SudachiPy (Shared Logic)
We use `sudachidict_core` with SudachiPy to split Japanese text into tokens.

**Code Location**: `shared/src/shared/analyzer.py`

Example:
- Input: `東京都へ行く`
- Output tokens: `東京都 へ 行く`

This logic is shared by:
- **Indexer Service**: Tokenizes content before writing to the inverted index.
- **Frontend Service**: Tokenizes user queries before searching.

### 2. Indexing Strategy (Custom Inverted Index)
Tokens are stored in the `inverted_index` table alongside per-token statistics:
- `inverted_index` for token → document matches
- `token_stats` and `index_stats` for BM25 scoring

This keeps indexing logic explicit and predictable, with full control over scoring and ranking.

### 3. Query Processing
Search queries are analyzed with the same tokenizer and matched against the inverted index tables. For hybrid search, the token-based results are combined with embedding-based results using Reciprocal Rank Fusion (RRF).

## Development Notes
- **Dictionary**: Uses `sudachidict_core` by default.
- **Performance**: Tokenization happens in Python before database writes and reads.
