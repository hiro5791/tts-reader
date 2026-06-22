"""読み上げアプリの中身（TTSエンジン部分）をまとめたパッケージ。

外から使うのは、この4つだけでよい。
"""

from .adapter import (
    synthesize,
    synthesize_clone,
    list_voices,
    default_voice,
    list_languages,
    default_language,
    ENGINES,
)

__all__ = [
    "synthesize",
    "synthesize_clone",
    "list_voices",
    "default_voice",
    "list_languages",
    "default_language",
    "ENGINES",
]
