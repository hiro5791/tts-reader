"""Irodori-TTS アダプタ。

Irodori は Python から直接呼ぶ部品（ライブラリ）が無く、
GitHub のリポジトリにある infer.py をコマンドとして実行して使う。
そこで、このアダプタは「infer.py を裏で実行して、出来た wav を返す」だけにする。

事前準備（setup_irodori で自動化する）:
  - vendor/Irodori-TTS にリポジトリを clone 済み
  - その中で `uv sync` 済み（必要なライブラリが入っている）
"""

from __future__ import annotations

import datetime as _dt
import subprocess
from pathlib import Path

# ---- 固定設定 ----------------------------------------------------------------

# Irodori のモデル（HuggingFace 上の名前）
HF_CHECKPOINT = "Aratako/Irodori-TTS-500M-v3"

# clone してきた Irodori-TTS リポジトリの場所
IRODORI_DIR = Path(__file__).resolve().parent.parent / "vendor" / "Irodori-TTS"

# 出力先フォルダ
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

# ------------------------------------------------------------------------------


def synthesize(text: str) -> str:
    """日本語テキストを Irodori-TTS で読み上げ、wav ファイルのパスを返す。"""
    if not IRODORI_DIR.exists():
        raise FileNotFoundError(
            "Irodori-TTS がまだ用意されていません。\n"
            f"（{IRODORI_DIR} が見つかりません）\n"
            "先に scripts/setup_irodori を実行して、Irodori を準備してください。"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = OUTPUT_DIR / f"irodori_{stamp}.wav"

    # uv 管理の環境で infer.py を、参照音声なし（--no-ref）で実行する
    cmd = [
        "uv", "run", "--no-sync", "python", "infer.py",
        "--hf-checkpoint", HF_CHECKPOINT,
        "--text", text,
        "--no-ref",
        "--output-wav", str(out_path),
    ]
    print(f"[Irodori] 実行: {' '.join(cmd[:6])} ...（初回はモデル読み込みで時間がかかります）")

    result = subprocess.run(
        cmd,
        cwd=str(IRODORI_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0 or not out_path.exists():
        # 失敗の中身を分かる形で投げる（UI でそのまま見える）
        raise RuntimeError(
            "Irodori-TTS の実行に失敗しました。\n"
            f"--- 標準出力 ---\n{result.stdout[-2000:]}\n"
            f"--- エラー出力 ---\n{result.stderr[-2000:]}"
        )

    print(f"[Irodori] 音声を書き出しました: {out_path}")
    return str(out_path)
