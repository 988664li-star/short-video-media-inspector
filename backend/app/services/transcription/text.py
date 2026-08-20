"""Transcript text normalization shared by recognition, punctuation, and cache reads."""

from __future__ import annotations


class TranscriptTextNormalizer:
    """Normalize punctuation glyphs without attempting language-model punctuation."""

    def __init__(self, language: str) -> None:
        self.language = language

    def normalize(self, text: str) -> str:
        punctuation = {"﹑": "，", "､": "，"}
        if self.language == "zh":
            punctuation.update(
                {
                    ",": "，",
                    ".": "。",
                    "!": "！",
                    "?": "？",
                    ";": "；",
                    ":": "：",
                }
            )
        return text.strip().translate(str.maketrans(punctuation))
