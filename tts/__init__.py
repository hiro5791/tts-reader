"""読み上げアプリの中身（TTSエンジン部分）をまとめたパッケージ。

外から使うのは adapter.synthesize() だけでよい。
"""

from .adapter import synthesize, ENGINES

__all__ = ["synthesize", "ENGINES"]
