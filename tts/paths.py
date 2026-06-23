"""書き込み可能なデータ保存先を一元管理する。

配布版（PyInstaller/MSIX）はインストール先が読み取り専用のため、出力 wav や設定ファイルを
そこに書くと失敗する。そこで、frozen のときは「ユーザーごとの書き込み可能フォルダ」
（%LOCALAPPDATA%\\MultiVoiceStudio、無ければホーム配下）に保存する。
開発時（非 frozen）は従来どおりプロジェクト直下に置く（挙動を変えない）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIRNAME = "MultiVoiceStudio"


def data_root() -> Path:
    """書き込み可能なデータ保存のルート。"""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        root = Path(base) / APP_DIRNAME
    else:
        # 開発時：プロジェクト直下（tts/ の親）
        root = Path(__file__).resolve().parent.parent
    root.mkdir(parents=True, exist_ok=True)
    return root


def outputs_dir() -> Path:
    """生成した wav の出力先（書き込み可能）。"""
    d = data_root() / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    return d
