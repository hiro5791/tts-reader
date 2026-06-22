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
import shutil
import site
import subprocess
import sys
from pathlib import Path


def _find_uv() -> str:
    """uv コマンドの場所を探す。PATH に無くても見つけられるようにする。"""
    found = shutil.which("uv")
    if found:
        return found
    # pip install --user で入れた場合の場所も探す
    candidates = [
        Path(site.getuserbase()) / "Scripts" / "uv.exe",   # Windows --user
        Path(site.getuserbase()) / "bin" / "uv",           # Linux/mac --user
        Path(sys.prefix) / "Scripts" / "uv.exe",           # venv 内
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    # 最後の手段：python -m uv で動かす
    return ""

# ---- 固定設定 ----------------------------------------------------------------

# Irodori のモデル（HuggingFace 上の名前）
# - 基本（参照音声タイプ）のモデル
HF_CHECKPOINT = "Aratako/Irodori-TTS-500M-v3"
# - caption（声の説明文）で声を作る VoiceDesign タイプのモデル
HF_CHECKPOINT_VOICEDESIGN = "Aratako/Irodori-TTS-600M-v3-VoiceDesign"

# clone してきた Irodori-TTS リポジトリの場所
IRODORI_DIR = Path(__file__).resolve().parent.parent / "vendor" / "Irodori-TTS"

# 用意した参照音声（声プリセット）の置き場所
VOICES_DIR = Path(__file__).resolve().parent.parent / "voices" / "irodori"

# 出力先フォルダ
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

# ---- 選べる声 ----------------------------------------------------------------
# 声の定義はこの VOICES 辞書 1か所にまとめる（編集・追加はここだけでよい）。
# 各声は次のどれかの形にする：
#   {"label_key": 表示名キー, "ref": None}        … 基本Irodori・参照なし（--no-ref）
#   {"label_key": 表示名キー, "ref": "xxx.wav"}   … 基本Irodori・voices/irodori/xxx.wav を参照音声に使う
#   {"label_key": 表示名キー, "caption": "説明文"} … VoiceDesign タイプ。説明文どおりの声を作る
#
# label_key は i18n.py の辞書のキー。表示名は表示言語の切り替えに追従する。
# caption を持つ声は、自動的に VoiceDesign モデル（HF_CHECKPOINT_VOICEDESIGN）に
# 切り替え、infer.py に  --caption "説明文" --no-ref  を渡して生成する。
# caption の文面を直したいときも、この辞書を書き換えるだけでよい。
DEFAULT_VOICE = "default"
VOICES = {
    # デフォルト（指定なし）：基本Irodori・参照なし
    "default": {
        "label_key": "voice_irodori_default",
        "ref": None,
    },
    # ↓ caption（声の説明文）で作る3種類の声
    "calm_female": {
        "label_key": "voice_irodori_calm_female",
        "caption": "落ち着いた女性の声で、近い距離感でやわらかく自然に読み上げてください。",
    },
    "bright_male": {
        "label_key": "voice_irodori_bright_male",
        "caption": "明るくはきはきした男性の声で、少し速めに元気よく読み上げてください。",
    },
    "gentle_neutral": {
        "label_key": "voice_irodori_gentle_neutral",
        "caption": "穏やかで中性的な声で、ゆっくり落ち着いて丁寧に読み上げてください。",
    },
}

# ---- 音声の言語 --------------------------------------------------------------
# Irodori は日本語のみ対応。UI 側ではこの1件だけになり、選択は日本語に固定される。
# (表示名の i18n キー, 言語名)
LANGUAGES = [("audiolang_japanese", "Japanese")]
DEFAULT_LANGUAGE = "Japanese"

# ------------------------------------------------------------------------------


def list_voices() -> list[tuple[str, str]]:
    """選べる声の一覧 (表示名の i18n キー, 声ID) を返す。"""
    return [(cfg["label_key"], vid) for vid, cfg in VOICES.items()]


def list_languages() -> list[tuple[str, str]]:
    """選べる音声の言語の一覧 (表示名の i18n キー, 言語名) を返す。Irodori は日本語のみ。"""
    return list(LANGUAGES)


def synthesize(text: str, voice: str = DEFAULT_VOICE, speed: float = 1.0,
               language: str = DEFAULT_LANGUAGE) -> str:
    """日本語テキストを Irodori-TTS で読み上げ、wav ファイルのパスを返す。

    voice    … 声ID（VOICES のキー）。"default" は参照なし。
    speed    … 1.0 が等倍。Irodori 側の --duration-scale で速度を変える（ピッチ保持）。
    language … 互換のため受け取るが、Irodori は日本語のみ対応のため使わない。
    """
    if not IRODORI_DIR.exists():
        raise FileNotFoundError(
            "Irodori-TTS がまだ用意されていません。\n"
            f"（{IRODORI_DIR} が見つかりません）\n"
            "先に scripts/setup_irodori を実行して、Irodori を準備してください。"
        )

    if voice not in VOICES:
        voice = DEFAULT_VOICE
    cfg = VOICES[voice]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = OUTPUT_DIR / f"irodori_{stamp}.wav"

    # 速度 → duration-scale に変換する。
    # duration-scale は「>1 で長く（遅く）、<1 で短く（速く）」なので、
    # 速度の逆数を渡す（speed=2.0 → duration_scale=0.5 で2倍速）。
    speed = max(0.1, float(speed))
    duration_scale = round(1.0 / speed, 3)

    # 声の種類に応じて、使うモデルと引数を切り替える。
    #   caption あり … VoiceDesign モデルで「説明文どおりの声」を作る（--caption ... --no-ref）
    #   caption なし … 基本Irodori。ref があれば参照音声、無ければ参照なし（--no-ref）
    caption = cfg.get("caption")
    if caption:
        checkpoint = HF_CHECKPOINT_VOICEDESIGN
        voice_args = ["--caption", caption, "--no-ref"]
    else:
        checkpoint = HF_CHECKPOINT
        ref = cfg.get("ref")
        if ref is None:
            voice_args = ["--no-ref"]
        else:
            ref_path = VOICES_DIR / ref
            if not ref_path.exists():
                raise FileNotFoundError(f"参照音声が見つかりません: {ref_path}")
            voice_args = ["--ref-wav", str(ref_path)]

    # uv 管理の環境で infer.py を実行する
    uv = _find_uv()
    uv_prefix = [uv] if uv else [sys.executable, "-m", "uv"]
    cmd = [
        *uv_prefix, "run", "--no-sync", "python", "infer.py",
        "--hf-checkpoint", checkpoint,
        "--text", text,
        *voice_args,
        "--duration-scale", str(duration_scale),
        "--output-wav", str(out_path),
    ]
    print(f"[Irodori] 実行（声={voice}, モデル={checkpoint}, 速度={speed}, "
          f"duration-scale={duration_scale}）"
          " ...（初回はモデル読み込みで時間がかかります）")

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

    print(f"[Irodori] 音声を書き出しました（声={voice}, 速度={speed}）: {out_path}")
    return str(out_path)
