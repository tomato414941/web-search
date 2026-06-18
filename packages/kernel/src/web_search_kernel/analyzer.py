"""
Japanese Text Analyzer (Shared Kernel)

Tokenizes Japanese text using SudachiPy for the custom inverted index.
Used by both Frontend (Search) and Indexer services.
"""

import logging
from sudachipy import Dictionary, SplitMode

logger = logging.getLogger(__name__)

_SUDACHI_SAFE_INPUT_BYTES = 32_000

STOP_WORDS = frozenset(
    {
        # English
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "about",
        "between",
        "through",
        "during",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "so",
        "if",
        "than",
        "that",
        "this",
        "it",
        "its",
        "he",
        "she",
        "they",
        "we",
        "you",
        "i",
        "me",
        "my",
        "your",
        "his",
        "her",
        "our",
        "their",
        # Japanese particles / auxiliaries
        "の",
        "に",
        "は",
        "を",
        "た",
        "が",
        "で",
        "て",
        "と",
        "し",
        "れ",
        "さ",
        "ある",
        "いる",
        "も",
        "する",
        "から",
        "な",
        "こと",
        "として",
        "い",
        "や",
        "れる",
        "など",
        "なっ",
        "ない",
        "この",
        "ため",
        "その",
        "あっ",
        "よう",
        "また",
        "もの",
        "という",
        "あり",
        "まで",
        "られ",
        "なる",
        "へ",
        "か",
        "だ",
        "これ",
        "によって",
        "により",
        "おり",
        "より",
        "による",
        "ず",
        "なり",
        "られる",
        "において",
        "ば",
        "なかっ",
        "なく",
        "しかし",
        "について",
        "せ",
        "だっ",
        "でき",
        "それ",
        "・",
        "ほか",
        "です",
        "ます",
        "。",
        "、",
    }
)


class JapaneseAnalyzer:
    def __init__(self, mode: str = "A"):
        self.tokenizer = Dictionary().create()
        # Mode A: Shortest (High Recall e.g. 東京都 -> 東京, 都)
        # Mode C: Longest (High Precision e.g. 東京都 -> 東京都)
        if mode == "A":
            self.mode = SplitMode.A
        elif mode == "B":
            self.mode = SplitMode.B
        else:
            self.mode = SplitMode.C

    def tokenize(self, text: str) -> str:
        """
        Tokenize Japanese text into space-separated words.

        Raises:
            Exception: Re-raises tokenization errors after logging
        """
        if not text or not text.strip():
            return ""

        #  If no Japanese, return as-is
        if not self._is_japanese(text):
            return text.lower()

        try:
            surfaces = []
            for chunk in self._iter_tokenizer_chunks(text):
                tokens = self.tokenizer.tokenize(chunk, self.mode)
                surfaces.extend(
                    t.surface().lower() for t in tokens if t.surface().strip()
                )
            return " ".join(surfaces)
        except Exception as e:
            logger.error(
                f"Tokenization failed for text (len={len(text)}): {e}",
                exc_info=True,
            )
            raise

    def _iter_tokenizer_chunks(self, text: str):
        chunk: list[str] = []
        chunk_bytes = 0
        for char in text:
            char_bytes = len(char.encode("utf-8"))
            if chunk and chunk_bytes + char_bytes > _SUDACHI_SAFE_INPUT_BYTES:
                yield "".join(chunk)
                chunk = []
                chunk_bytes = 0
            chunk.append(char)
            chunk_bytes += char_bytes
        if chunk:
            yield "".join(chunk)

    def _is_japanese(self, text: str) -> bool:
        # Check for Hiragana, Katakana, or Common CJK Unified Ideographs
        # Hiragana: 3040-309F
        # Katakana: 30A0-30FF
        # Kanji: 4E00-9FFF
        for char in text:
            code = ord(char)
            if (
                (0x3040 <= code <= 0x309F)
                or (0x30A0 <= code <= 0x30FF)
                or (0x4E00 <= code <= 0x9FFF)
            ):
                return True
        return False


# Global instance
analyzer = JapaneseAnalyzer(mode="A")
