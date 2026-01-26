"""
Japanese Text Analyzer (Shared Kernel)

Tokenizes Japanese text using SudachiPy for FTS5 indexing.
Used by both Frontend (Search) and Indexer services.
"""

import logging
from sudachipy import Dictionary, SplitMode

logger = logging.getLogger(__name__)


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
            return text

        try:
            tokens = self.tokenizer.tokenize(text, self.mode)
            surfaces = [t.surface() for t in tokens if t.surface().strip()]
            return " ".join(surfaces)
        except Exception as e:
            logger.error(
                f"Tokenization failed for text (len={len(text)}): {e}",
                exc_info=True,
            )
            raise

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
