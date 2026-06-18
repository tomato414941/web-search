from web_search_kernel import analyzer as analyzer_module
from web_search_kernel.analyzer import JapaneseAnalyzer


class _Token:
    def __init__(self, surface: str):
        self._surface = surface

    def surface(self) -> str:
        return self._surface


class _RecordingTokenizer:
    def __init__(self):
        self.inputs: list[str] = []

    def tokenize(self, text: str, mode):
        self.inputs.append(text)
        return [_Token(text)]


def test_tokenize_splits_long_japanese_text(monkeypatch):
    tokenizer = _RecordingTokenizer()
    analyzer = JapaneseAnalyzer.__new__(JapaneseAnalyzer)
    analyzer.tokenizer = tokenizer
    analyzer.mode = object()

    monkeypatch.setattr(analyzer_module, "_SUDACHI_SAFE_INPUT_BYTES", 12)

    result = analyzer.tokenize("日本語日本語日本語")

    assert result == "日本語日 本語日本 語"
    assert [len(value.encode("utf-8")) for value in tokenizer.inputs] == [12, 12, 3]
