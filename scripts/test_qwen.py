"""Qwen3-TTS が単体で動くかの確認用スクリプト。

UI を使わずに、固定の日本語テキストを wav にして保存するだけ。
これが成功すれば、Qwen のアダプタは正しく動いている。

実行（PowerShell、プロジェクト直下で）:
    python scripts/test_qwen.py
"""

import sys
from pathlib import Path

# プロジェクト直下を import できるようにする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tts import synthesize  # noqa: E402

if __name__ == "__main__":
    text = "こんにちは。これは読み上げアプリのテストです。日本語をきちんと読み上げられるか確認しています。"
    print("Qwen3-TTS で読み上げを試します...")
    path = synthesize(text, "qwen3")
    print(f"成功しました。音声ファイル: {path}")
